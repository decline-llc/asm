"""Real capability adapters; each HTTP hop/browser request checks current policy."""
import copy
import base64
import hashlib
import ipaddress
import json
import os
import re
import time
import uuid
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from .db import Database
from .models import utcnow
from .panel.base import RateLimiter, QuotaExceeded
from .policy import redacted_snapshot
from .run_store import atomic_json, digest
from .scope import normalize_host


class ExecutionContext:
    def __init__(self, workbench, run, step):
        self.workbench, self.run, self.step = workbench, run, step
        self.target = step["target"]
        self.capability = step["capability"]
        self.params = copy.deepcopy(step["params"])
        self.policy = workbench._policy(run)
        self.last_evidence_id = None
        self.active_call_id = None
        self.records = []
        self.output_directory = Path(run["directory"]) / "evidence" / (step["id"] + "-" + str(step["attempt"] + 1))
        self.output_directory.mkdir(parents=True, exist_ok=True)
        capability_steps = {s["id"] for s in run["steps"] if s["capability"] == self.capability}
        self.calls = sum(1 for e in workbench.store.events(run["run_id"]) if e["kind"] == "tool_started" and e["data"].get("step_id") in capability_steps)

    def check_control(self):
        self.workbench.check_control(self.run["run_id"])

    def wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.check_control()
            time.sleep(min(0.1, max(0, end - time.monotonic())))

    def require(self, target=None, *, network=True, target_kind=None):
        self.check_control()
        target = target or self.target
        if target_kind is None:
            if self.capability == "company_lookup":
                target_kind = "subject"
            elif self.capability in {"search", "osint", "passive_supply_chain"}:
                current = self.policy._current()
                scope_ref = current.get("permissions", {}).get(self.capability, {}).get("scope_ref", "investigation")
                target_kind = next((kind for kind in ("subject", "query", "brand")
                    if self.policy.contains(scope_ref, target, target_kind=kind)), None)
                if target_kind is None:
                    try:
                        host = normalize_host(target)
                        target_kind = "host" if "." in host or host == "localhost" or _is_ip(host) else "query"
                    except ValueError:
                        target_kind = "query"
            else:
                target_kind = "host"
        budget = self.run["config"].get("budgets", {})
        from datetime import datetime, timezone
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(self.run["started_at"])).total_seconds()
        available = elapsed <= float(budget.get("max_duration_seconds", 7200))
        cap_calls = int(budget.get("per_tool", {}).get(self.capability, {}).get("max_calls", 100000))
        available = available and self.calls <= cap_calls
        return self.policy.require(self.capability, target, target_kind=target_kind,
            tool=self.step["tool"] if self.policy.tool_for(self.capability) else None,
            network=network, budget_available=available)

    def record(self, tool, params, status, outputs, provenance, *, conn=None, call_id=None):
        data = {"call_id": call_id or uuid.uuid4().hex, "ts": utcnow(), "step_id": self.step["id"],
                "tool": tool, "params": redacted_snapshot(params), "status": status,
                "outputs": outputs, "provenance": provenance}
        self.workbench.store.event(self.run["run_id"], "tool_call", data, conn=conn)
        if conn is None:
            self.workbench.store.flush_logs(self.run["run_id"], self.run["directory"])
        return data

    def call(self, tool, params, operation):
        self.check_control()
        action_id = digest([self.run["run_id"], self.step["id"], tool, redacted_snapshot(params)])
        def reuse_receipt(row):
            path = Path(row["path"])
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("Completed action evidence is missing or has changed; manual review required")
            self.last_evidence_id = row["evidence_id"]
            return json.loads(path.read_text(encoding="utf-8"))
        cached = self.workbench.store.rows("SELECT * FROM action_receipts WHERE id=?", (action_id,))
        if cached:
            return reuse_receipt(cached[0])
        call_id = uuid.uuid4().hex
        cap_calls = int(self.run["config"].get("budgets", {}).get("per_tool", {}).get(self.capability, {}).get("max_calls", 100000))
        with self.workbench.store.connection() as conn:
            self.check_control()
            # A parallel action may have committed its receipt since the first read.
            cached = conn.execute("SELECT * FROM action_receipts WHERE id=?", (action_id,)).fetchone()
            if cached is not None:
                return reuse_receipt(cached)
            capability_steps = {row["id"] for row in conn.execute("SELECT id FROM steps WHERE run=? AND capability=?",
                (self.run["run_id"], self.capability))}
            used = sum(json.loads(row["data"]).get("step_id") in capability_steps for row in conn.execute(
                "SELECT data FROM events WHERE run=? AND kind='tool_started'", (self.run["run_id"],)))
            if used >= cap_calls:
                from .policy import PolicyDenied
                raise PolicyDenied("tool_call_budget_exhausted")
            self.calls = used + 1
            self.workbench.store.event(self.run["run_id"], "tool_started", {"call_id": call_id,
                "step_id": self.step["id"], "tool": tool, "params": redacted_snapshot(params), "ts": utcnow(),
                "request_ledger_version": 1}, conn=conn)
        previous_call_id, self.active_call_id = self.active_call_id, call_id
        try:
            value = operation()
        except BaseException as exc:
            path = self.output_directory / (call_id + ".error.json")
            atomic_json(path, {"error_type": type(exc).__name__, "tool": tool})
            self._evidence(call_id, path, "tool_error")
            exhausted = isinstance(exc, QuotaExceeded) or (type(exc).__name__ == "PolicyDenied" and "budget" in str(exc))
            self.record(tool, params, "quota-exhausted" if exhausted else "interrupted" if type(exc).__name__ == "RunControlled" else "failed",
                        [path.relative_to(self.run["directory"]).as_posix()], {"source": "live", "error_type": type(exc).__name__})
            raise
        finally:
            self.active_call_id = previous_call_id
        path = self.output_directory / (call_id + ".json")
        atomic_json(path, redacted_snapshot(value))
        self._evidence(call_id, path, "tool_output")
        with self.workbench.store.connection() as conn:
            conn.execute("INSERT INTO action_receipts VALUES(?,?,?,?,?,?)", (action_id, self.run["run_id"], self.step["id"], str(path), call_id, hashlib.sha256(path.read_bytes()).hexdigest()))
            self.record(tool, params, "completed", [path.relative_to(self.run["directory"]).as_posix()], {"source": "live", "observed_at": utcnow()}, conn=conn, call_id=call_id)
        self.workbench.store.flush_logs(self.run["run_id"], self.run["directory"])
        return value

    def _evidence(self, evidence_id, path, kind):
        self.last_evidence_id = evidence_id
        record = {"category": "evidence_index", "evidence_id": evidence_id,
            "path": path.relative_to(self.run["directory"]).as_posix(), "kind": kind,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "observed_at": utcnow()}
        self.records.append(record)
        # Persist immediately so interruption retains evidence even before a step receipt exists.
        with self.workbench.store.connection() as conn:
            conn.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?)",
                (evidence_id, self.run["run_id"], "evidence_index", json.dumps(record, ensure_ascii=False)))
            self.workbench.store.event(self.run["run_id"], "artifact_written", record, conn)

    def reserve_http_request(self, url, *, method="GET", transport="target_http", resource_type=""):
        """Reserve one physical attempt durably, across steps, retries and workers.

        The caller invokes this only inside an uncached action immediately before
        transmitting. Failed attempts and pre-ledger HTTP actions count conservatively.
        """
        from .policy import PolicyDenied
        self.require(url)
        host = normalize_host(url)
        configured = self.params.get("max_requests_per_host")
        limit = int(configured) if configured is not None else None
        if limit is not None and limit <= 0:
            raise ValueError("max_requests_per_host must be a positive integer")
        denied = False
        with self.workbench.store.connection() as conn:
            self.require(url)
            events = [json.loads(row["data"]) for row in conn.execute(
                "SELECT data FROM events WHERE run=? AND kind='physical_request_started'", (self.run["run_id"],))]
            completed_attempt_ids = {row.get("call_id") for row in events}
            blocked = [json.loads(row["data"]) for row in conn.execute(
                "SELECT data FROM events WHERE run=? AND kind='physical_request_blocked'", (self.run["run_id"],))]
            completed_attempt_ids.update(row.get("call_id") for row in blocked)
            completed_attempt_ids.add(self.active_call_id)
            used = sum(row.get("capability") == self.capability and row.get("host") == host for row in events)
            # Old runs have target_http starts but no physical-request ledger yet.
            # Account for them once without replaying a request or resetting allowance.
            steps = {row["id"] for row in conn.execute("SELECT id FROM steps WHERE run=? AND capability=?",
                (self.run["run_id"], self.capability))}
            legacy = 0
            for row in conn.execute("SELECT data FROM events WHERE run=? AND kind='tool_started'", (self.run["run_id"],)):
                old = json.loads(row["data"])
                if (old.get("request_ledger_version") == 1 or old.get("tool") not in {"target_http", "playwright"}
                        or old.get("step_id") not in steps or old.get("call_id") in completed_attempt_ids):
                    continue
                try:
                    same_host = normalize_host(old.get("params", {}).get("url", "")) == host
                except ValueError:
                    same_host = False
                # A legacy browser call can have unknown subrequest count. Treat
                # its configured host allowance as consumed instead of resetting it.
                legacy += (limit or 1) if same_host and old.get("tool") == "playwright" else same_host
            used += legacy
            data = {"request_id": uuid.uuid4().hex, "call_id": self.active_call_id, "step_id": self.step["id"],
                "capability": self.capability, "host": host, "url": redacted_snapshot(url), "method": method,
                "transport": transport, "resource_type": resource_type, "limit": limit,
                "used": used, "legacy_assumed_attempts": legacy, "ts": utcnow()}
            if limit is not None and used >= limit:
                data["reason"] = "http_request_budget_exhausted"
                self.workbench.store.event(self.run["run_id"], "physical_request_blocked", data, conn=conn)
                denied = True
            else:
                data["used"] = used + 1
                self.workbench.store.event(self.run["run_id"], "physical_request_started", data, conn=conn)
        if denied:
            raise PolicyDenied("http_request_budget_exhausted")
        # A reservation never restores an authorization revoked while it committed.
        self.require(url)

    def http(self, url, *, method="GET", capability=None, max_response_bytes=None, request_headers=None,
             follow_redirects=True, transport="target_http"):
        capability = capability or self.capability
        params = self.params
        max_bytes = int(max_response_bytes or params.get("max_response_bytes", self.run["config"].get("web", {}).get("max_response_bytes", 65536)))
        timeout = float(params.get("timeout_seconds", 15))
        redirects = int(params.get("max_redirects", 5))
        rate = float(params.get("requests_per_second", 2))
        for _ in range(redirects + 1):
            self.require(url)
            self.wait(1 / max(rate, 0.01))
            self.require(url)
            def request():
                with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                    self.reserve_http_request(url, method=method, transport=transport)
                    self.require(url)
                    with client.stream(method, url, headers={"User-Agent": "ASM-Workbench/0.2", **(request_headers or {})}) as reply:
                        body = bytearray()
                        for chunk in reply.iter_bytes(chunk_size=min(max_bytes, 16384)):
                            self.check_control()
                            body.extend(chunk[:max_bytes - len(body)])
                            if len(body) >= max_bytes:
                                break
                        return {"url": str(reply.url), "status": reply.status_code,
                            "headers": {k: v for k, v in reply.headers.items() if k.lower() not in {"set-cookie", "authorization", "proxy-authorization"}},
                            "body": body.decode("utf-8", errors="replace"), "body_base64": base64.b64encode(body).decode(), "truncated": len(body) >= max_bytes}
            call_params = {"url": url, "method": method, "capability": capability}
            if not follow_redirects:
                call_params["follow_redirects"] = False
            if max_response_bytes is not None:
                # A pre-upgrade interrupted JS step may already have the larger raw
                # response. Reuse that immutable receipt and restrict parsing locally.
                legacy_action = digest([self.run["run_id"], self.step["id"], "target_http", redacted_snapshot(call_params)])
                legacy_cached = not request_headers and self.workbench.store.rows("SELECT id FROM action_receipts WHERE id=?", (legacy_action,))
                if not legacy_cached:
                    call_params["max_response_bytes"] = max_bytes
            if request_headers:
                call_params["headers"] = request_headers
            reply = self.call("target_http", call_params, request)
            if max_response_bytes is not None:
                encoded = reply["body"].encode("utf-8")
                if len(encoded) >= max_bytes:
                    reply = {**reply, "body": encoded[:max_bytes].decode("utf-8", errors="ignore"), "truncated": True}
            reply["evidence_id"] = self.last_evidence_id
            if follow_redirects and reply["status"] in {301, 302, 303, 307, 308} and reply["headers"].get("location"):
                url = urljoin(url, reply["headers"]["location"])
            else:
                return reply
        raise ValueError("Redirect limit exceeded")


def result(ctx, assets=None, records=None, status="completed", reason=""):
    return {"status": status, "reason": reason, "assets": assets or [], "records": (records or []) + ctx.records}


def web_asset(reply, *, source="target_http", verified=True):
    parsed = urlsplit(reply["url"])
    match = re.search(r"<title[^>]*>(.*?)</title>", reply.get("body", ""), re.I | re.S)
    title = re.sub(r"\s+", " ", match[1]).strip() if match else ""
    ip = parsed.hostname if _is_ip(parsed.hostname) else ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return {"asset_id": digest([parsed.hostname, port, "tcp"])[:24], "asset_type": "web_endpoint",
        "name": parsed.hostname, "domain": "" if ip else parsed.hostname, "ip": ip, "port": port,
        "protocol": "tcp", "url": reply["url"], "title": title, "http_status": reply["status"],
        "technology": reply.get("headers", {}).get("server", ""), "sources": [source],
        "verification_status": "verified" if verified else "candidate_only", "confidence": "A" if verified else "C",
        "attribution_status": "unconfirmed", "observed_at": utcnow(),
        "evidence_ids": [reply["evidence_id"]] if reply.get("evidence_id") else []}


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False


def web_visit(ctx):
    reply = ctx.http(ctx.target)
    asset = web_asset(reply)
    return result(ctx, [asset], [{"category": "web_endpoints", **asset, "response_bytes": len(reply["body"].encode())}])


def canonical_web_url(value, base=None):
    """Fragments do not identify a new HTTP request; credential URLs are rejected."""
    parsed = urlsplit(urljoin(base, value) if base else value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Expected a credential-free HTTP URL")
    if redacted_snapshot(parsed.geturl()) != parsed.geturl():
        raise ValueError("Credential-bearing URL queries are not accepted")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    port = parsed.port
    if port and port != (443 if parsed.scheme == "https" else 80):
        host += ":" + str(port)
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", parsed.query, ""))


class Links(HTMLParser):
    def __init__(self, text, base):
        super().__init__()
        self.base, self.links, self.scripts, self.rejected = base, [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get("src") if tag == "script" else attrs.get("href") if tag == "a" else None
        if value:
            try:
                url = canonical_web_url(value, self.base)
            except ValueError:
                if value.startswith(("http://", "https://", "//")):
                    self.rejected.append("unsafe_or_invalid_url")
                return
            collection = self.scripts if tag == "script" else self.links
            if url not in collection:
                collection.append(url)


def _lead(url, decision, evidence_ids=(), **extra):
    if decision.reason not in {"outside_function_scope", "target_local_only"}:
        return {"category": "scope_and_coverage", "feature": decision.capability, "target": url,
            "status": "not_requested", "reason": decision.reason, "evidence_ids": list(evidence_ids), **extra}
    return {"category": "out_of_scope_leads", "name": url, "url": url,
        "scope_status": "out_of_scope", "reason": decision.reason, "verification_status": "candidate_only",
        "evidence_ids": list(evidence_ids), "next_step": "Manually add investigation scope before further collection", **extra}


def web_crawl(ctx):
    if ctx.step["tool"] != "native_crawler":
        return result(ctx, status="blocked", reason="selected_crawler_adapter_not_integrated")
    max_depth = int(ctx.params.get("max_depth", 2))
    limit = int(ctx.params.get("max_urls_per_host", 200))
    queue, visited, assets, records, counts = [(canonical_web_url(ctx.target), 0)], set(), [], [], {}
    total_limit = int(ctx.params.get("max_urls_total", limit * int(ctx.run["config"].get("budgets", {}).get("max_hosts", 1000))))
    if total_limit <= 0:
        return result(ctx, status="blocked", reason="invalid_max_urls_total")
    while queue and len(visited) < total_limit:
        ctx.check_control()
        url, depth = queue.pop(0)
        if url in visited:
            continue
        host = normalize_host(url)
        if counts.get(host, 0) >= limit:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": url,
                "status": "not_requested", "reason": "max_urls_per_host_exhausted"})
            continue
        visited.add(url)
        counts[host] = counts.get(host, 0) + 1
        reply = ctx.http(url)
        asset = web_asset(reply)
        assets.append(asset)
        records.append({"category": "web_endpoints", **asset, "depth": depth})
        links = Links(reply["body"], reply["url"])
        if links.rejected:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": reply["url"],
                "status": "not_requested", "reason": "unsafe_or_invalid_link", "rejected_count": len(links.rejected)})
        for link in links.links:
            approved = ctx.policy.check(ctx.capability, link, tool=ctx.step["tool"])
            if approved.allowed:
                if depth < max_depth:
                    if link not in visited:
                        queue.append((link, depth + 1))
                elif link not in visited:
                    records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": link,
                        "status": "not_requested", "reason": "max_depth_exhausted", "evidence_ids": [reply["evidence_id"]]})
            else:
                records.append(_lead(link, approved, [reply["evidence_id"]]))
    if queue:
        records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": ctx.target,
            "status": "not_requested", "reason": "max_urls_total_exhausted", "remaining_urls": len(queue)})
    return result(ctx, assets, records)


def js_analysis(ctx):
    if ctx.step["tool"] != "native_js_analyzer":
        return result(ctx, status="blocked", reason="selected_js_adapter_not_integrated")
    if ctx.params.get("verify_discovered_endpoints", False):
        return result(ctx, status="blocked", reason="endpoint_verification_requires_separate_selected_web_visit")
    reply = ctx.http(ctx.target)
    scripts = Links(reply["body"], reply["url"]).scripts
    records, counts, found = [], {}, set()
    limit = int(ctx.params.get("max_files_per_host", 50))
    for script in scripts:
        ctx.check_control()
        decision = ctx.policy.check(ctx.capability, script, tool=ctx.step["tool"])
        if not decision.allowed:
            records.append(_lead(script, decision, [reply["evidence_id"]], relationship="script_resource"))
            continue
        host = normalize_host(script)
        if counts.get(host, 0) >= limit:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": script,
                "status": "not_requested", "reason": "max_files_per_host_exhausted"})
            continue
        counts[host] = counts.get(host, 0) + 1
        content = ctx.http(script, max_response_bytes=int(ctx.params.get("max_bytes_per_file", 1048576)))
        if content["truncated"]:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": script,
                "status": "partial", "reason": "max_bytes_per_file_exhausted", "evidence_ids": [content["evidence_id"]]})
        endpoints = sorted(set(re.findall(r'''["']((?:https?://|/api/)[^\s"']{1,512})["']''', content["body"])))
        for endpoint in endpoints:
            try:
                url = canonical_web_url(endpoint, script)
            except ValueError:
                continue
            if url in found:
                continue
            found.add(url)
            decision = ctx.policy.check(ctx.capability, url, tool=ctx.step["tool"])
            if not decision.allowed:
                records.append(_lead(url, decision, [content["evidence_id"]], relationship="javascript_endpoint_string"))
                continue
            records.append({"category": "web_endpoints", "url": url, "source": script,
                "verification_status": "candidate_only", "remarks": "JS string candidate; endpoint not requested", "evidence_ids": [content["evidence_id"]]})
    return result(ctx, records=records)


PATHS = ["/login", "/robots.txt", "/sitemap.xml", "/swagger.json", "/.git/HEAD", "/backup.zip", "/actuator/env"]
EXPOSURES = {"public_configuration": ["/actuator/env"], "exposed_backups": ["/backup.zip"],
    "source_control_metadata": ["/.git/HEAD"], "middleware_management": ["/server-status", "/phpinfo.php"], "public_api_schema": ["/swagger.json"]}


def web_paths(ctx):
    dictionary = ctx.params.get("dictionary", "built_in_basic")
    if dictionary == "built_in_basic":
        paths = PATHS
    elif isinstance(dictionary, str) and dictionary.startswith("seclists:"):
        from .external_tools import frozen_dictionary
        paths = ["/" + value.lstrip("/") for value in frozen_dictionary(ctx, dictionary, PATHS)]
    else:
        file = (ctx.workbench.root / dictionary).resolve()
        if not file.is_relative_to(ctx.workbench.root) or not file.is_file() or file.name.startswith(".env"):
            return result(ctx, status="blocked", reason="dictionary_missing_or_invalid")
        paths = [p.strip() for p in file.read_text(encoding="utf-8").splitlines() if p.strip()]
    baseline = ctx.http(urljoin(ctx.target, "/asm-missing-" + digest(ctx.step["id"])[:24])) if ctx.params.get("include_random_baseline", True) else None
    signatures = {(baseline["status"], digest(baseline["body"]))} if baseline else set()
    assets, records = [], []
    for path in paths[:int(ctx.params.get("max_requests_per_host", 1000))]:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Dictionary paths must be relative root paths")
        reply = ctx.http(urljoin(ctx.target, path))
        if reply["status"] != 404 and (reply["status"], digest(reply["body"])) not in signatures:
            asset = web_asset(reply)
            assets.append(asset)
            records.append({"category": "web_endpoints", **asset, "remarks": "Observed path; risk not confirmed"})
    return result(ctx, assets, records)


def exposure_check(ctx):
    checks = ctx.params.get("approved_checks", [])
    if not checks:
        return result(ctx, status="skipped", reason="empty_approved_checks")
    unknown = set(checks) - set(EXPOSURES)
    if unknown:
        return result(ctx, status="blocked", reason="unsupported_approved_checks:" + ",".join(sorted(unknown)))
    records = []
    baseline = ctx.http(urljoin(ctx.target, "/asm-missing-" + digest(ctx.step["id"])[:24]))
    for check in checks:
        for path in EXPOSURES[check]:
            reply = ctx.http(urljoin(ctx.target, path))
            if reply["status"] == 200 and digest(reply["body"]) != digest(baseline["body"]):
                records.append({"category": "findings", "finding_id": digest([ctx.target, check, path])[:24],
                    "kind": check, "url": reply["url"], "status": "review", "severity": "info",
                    "evidence_ids": [reply["evidence_id"]], "remarks": "Distinct accessible response; exposure candidate requires content review"})
    return result(ctx, records=records)


def vulnerability_check(ctx):
    if ctx.step["tool"] != "native_risk_checks":
        return result(ctx, status="blocked", reason="selected_risk_check_adapter_not_integrated")
    checks = ctx.params.get("approved_checks", [])
    if not checks:
        return result(ctx, status="skipped", reason="empty_approved_checks")
    if set(checks) - {"security_headers", "cors_policy"}:
        return result(ctx, status="blocked", reason="unsupported_approved_check_plugin")
    records = []
    limit = int(ctx.params.get("max_requests_per_host", 100))
    for index, check in enumerate(dict.fromkeys(checks)):
        ctx.check_control()
        if index >= limit:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": ctx.target,
                "status": "not_requested", "method": check, "reason": "max_requests_per_host_exhausted"})
            continue
        if check == "cors_policy":
            origin = "https://asm-origin.invalid"
            observed = ctx.http(ctx.target, request_headers={"Origin": origin})
        else:
            observed = ctx.http(ctx.target)
        headers = {k.lower(): v for k, v in observed["headers"].items()}
        missing = [h for h in ("content-security-policy", "x-content-type-options") if h not in headers] if check == "security_headers" else []
        cors_origin = headers.get("access-control-allow-origin", "")
        if missing or (check == "cors_policy" and cors_origin in {"*", origin}):
            records.append({"category": "findings", "finding_id": digest([ctx.target, check])[:24],
                "kind": check, "url": observed["url"], "status": "review", "knowledge": "observation",
                "severity": "low", "evidence_ids": [observed["evidence_id"]],
                "remarks": "Observed configuration candidate; impact requires review", "missing": missing,
                "basis": {"missing_headers": missing, "allow_origin": cors_origin,
                    "allow_credentials": headers.get("access-control-allow-credentials", "")}})
        else:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": observed["url"],
                "status": "observed", "method": check, "reason": "configured_candidate_condition_not_observed",
                "evidence_ids": [observed["evidence_id"]]})
    return result(ctx, records=records)


def takeover_probe(ctx):
    """Correlate saved CNAME observations and an approved HTTP fingerprint only."""
    if ctx.step["tool"] != "stage_5_takeover_fingerprint":
        return result(ctx, status="blocked", reason="selected_takeover_adapter_not_integrated")
    from .utils.constants import TAKEOVER_FINGERPRINTS
    providers = ctx.params.get("approved_providers", [])
    if not providers:
        return result(ctx, status="skipped", reason="empty_approved_providers")
    unknown = set(providers) - {entry[0] for entry in TAKEOVER_FINGERPRINTS}
    if unknown:
        return result(ctx, status="blocked", reason="unsupported_takeover_provider:" + ",".join(sorted(unknown)))
    if ctx.params.get("claim_external_resource") or not ctx.params.get("collect_fingerprint_only", True):
        return result(ctx, status="blocked", reason="only_fingerprint_collection_supported")
    url = canonical_web_url(ctx.target if "://" in ctx.target else "https://" + ctx.target)
    host = normalize_host(url)
    cname_evidence = []
    for row in ctx.workbench.store.rows("SELECT data FROM records WHERE run=? AND category='dns_observations'", (ctx.run["run_id"],)):
        observation = json.loads(row["data"])
        if observation.get("domain") != host:
            continue
        for answer in observation.get("answers", []):
            if answer.get("rtype") == "CNAME" and answer.get("accepted", True):
                cname_evidence.append((answer.get("value", "").rstrip(".").lower(), observation.get("evidence_ids", [])))
        if observation.get("record_type") == "CNAME" or observation.get("rtype") == "CNAME":
            cname_evidence.append((str(observation.get("value", "")).rstrip(".").lower(), observation.get("evidence_ids", [])))
    reply = ctx.http(url)
    records = []
    for provider, suffix, status, marker in TAKEOVER_FINGERPRINTS:
        if provider not in providers or reply["status"] != status or marker.lower() not in reply["body"].lower():
            continue
        matches = [(name, ids) for name, ids in cname_evidence if name == suffix or name.endswith("." + suffix)]
        ids = sorted({reply["evidence_id"], *(eid for _, values in matches for eid in values)})
        records.append({"category": "findings", "finding_id": digest([url, "takeover", provider])[:24],
            "kind": "takeover_fingerprint_candidate", "url": reply["url"], "provider": provider,
            "severity": "info", "status": "review", "knowledge": "candidate", "evidence_ids": ids,
            "basis": {"provider": provider, "http_status": reply["status"], "matched_marker": marker,
                "cname_matches": [name for name, _ in matches], "cname_corroborated": bool(matches)},
            "remarks": "Provider HTTP marker observed; takeover and resource availability are unverified. No resource claim attempted."})
    if not records:
        records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": url,
            "status": "observed", "reason": "approved_fingerprint_not_observed", "evidence_ids": [reply["evidence_id"]]})
    return result(ctx, records=records)


def auth_audit(ctx):
    """An explicit anonymous-access plan; no credentials or login attempts."""
    if ctx.step["tool"] != "native_auth_audit":
        return result(ctx, status="blocked", reason="selected_auth_adapter_not_integrated")
    checks = ctx.params.get("approved_checks", [])
    if not checks:
        return result(ctx, status="skipped", reason="empty_approved_checks")
    if set(checks) - {"anonymous_protected_paths"}:
        return result(ctx, status="blocked", reason="unsupported_auth_check_plugin")
    paths = ctx.params.get("protected_paths", [])
    denied = ctx.params.get("expected_denied_statuses", [401, 403])
    if not isinstance(paths, list) or not paths:
        return result(ctx, status="blocked", reason="explicit_protected_paths_required")
    if any(not isinstance(p, str) or not p.startswith("/") or p.startswith("//") for p in paths):
        return result(ctx, status="blocked", reason="protected_paths_must_be_relative_root_paths")
    if not isinstance(denied, list) or not denied or any(type(code) is not int or not 100 <= code <= 599 for code in denied):
        return result(ctx, status="blocked", reason="invalid_expected_denied_statuses")
    limit = int(ctx.params.get("max_requests_per_host", 100))
    records = []
    for path in list(dict.fromkeys(paths))[:limit]:
        ctx.check_control()
        requested = canonical_web_url(path, ctx.target)
        reply = ctx.http(requested)
        if canonical_web_url(reply["url"]) != requested:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": requested,
                "status": "inconclusive", "reason": "redirected_response_requires_review", "final_url": reply["url"],
                "http_status": reply["status"], "evidence_ids": [reply["evidence_id"]]})
        elif reply["status"] in denied:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": reply["url"],
                "status": "observed", "method": "anonymous_protected_paths", "reason": "configured_denial_status_observed",
                "http_status": reply["status"], "evidence_ids": [reply["evidence_id"]]})
        elif 200 <= reply["status"] < 300:
            records.append({"category": "findings", "finding_id": digest([ctx.target, "anonymous_access", path])[:24],
                "kind": "anonymous_access_candidate", "url": reply["url"], "status": "review", "severity": "info",
                "knowledge": "observation", "evidence_ids": [reply["evidence_id"]],
                "basis": {"http_status": reply["status"], "expected_denied_statuses": denied},
                "remarks": "Anonymous response accessible at an explicitly designated protected path; content and intended policy require review."})
        else:
            records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": reply["url"],
                "status": "inconclusive", "reason": "response_not_success_or_configured_denial", "http_status": reply["status"],
                "evidence_ids": [reply["evidence_id"]]})
    if len(set(paths)) > limit:
        records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": ctx.target,
            "status": "not_requested", "reason": "max_requests_per_host_exhausted"})
    return result(ctx, records=records)


def screenshot(ctx):
    from playwright.sync_api import sync_playwright
    from .orchestrator import RunControlled
    from .policy import PolicyDenied
    url = ctx.target
    ctx.require(url)
    blocked, block_details, controls = [], [], []
    def capture():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--disable-background-networking", "--disable-component-update", "--disable-sync"])
            try:
                context = browser.new_context(service_workers="block", accept_downloads=False)
                def route(route):
                    try:
                        ctx.reserve_http_request(route.request.url, method=route.request.method,
                            transport="playwright", resource_type=route.request.resource_type)
                        ctx.require(route.request.url)
                    except RunControlled as exc:
                        controls.append(exc)
                        route.abort()
                        return
                    except (ValueError, RuntimeError) as exc:
                        safe_url = redacted_snapshot(route.request.url)
                        blocked.append(safe_url)
                        block_details.append({"url": safe_url, "reason": str(exc) if isinstance(exc, PolicyDenied) else type(exc).__name__})
                        route.abort()
                        return
                    route.continue_()
                context.route("**/*", route)
                if hasattr(context, "route_web_socket"):
                    context.route_web_socket("**/*", lambda ws: ws.close())
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=int(ctx.params.get("timeout_seconds", 15) * 1000))
                except Exception:
                    if controls:
                        raise controls[0]
                    if any("budget" in row["reason"] for row in block_details):
                        raise PolicyDenied("http_request_budget_exhausted") from None
                    if block_details:
                        raise PolicyDenied("browser_request_scope_denied") from None
                    raise
                if controls:
                    raise controls[0]
                ctx.require(page.url)
                page_kind = "login" if page.locator('input[type="password"]').count() else "page"
                image = page.screenshot(full_page=ctx.params.get("full_page", True))
                path = ctx.output_directory / (uuid.uuid4().hex + ".png")
                path.write_bytes(image)
                ctx._evidence(uuid.uuid4().hex, path, "screenshot")
                if controls:
                    raise controls[0]
                ctx.check_control()
                return {"url": page.url, "title": page.title(), "screenshot_path": path.relative_to(ctx.run["directory"]).as_posix(),
                    "page_kind": page_kind, "page_kind_basis": "password_input_present" if page_kind == "login" else "no_password_input_observed",
                    "blocked_requests": blocked, "blocked_details": block_details}
            finally:
                browser.close()
    output = ctx.call("playwright", {"url": url, "full_page": ctx.params.get("full_page", True)}, capture)
    asset = web_asset({**output, "body": "", "status": None})
    limited = bool(output.get("blocked_requests"))
    login = output.get("page_kind") == "login"
    asset.update({"title": output["title"], "screenshot_path": output["screenshot_path"],
        "screenshot_kind": "login" if login else "page",
        "remarks": ("Login page screenshot; password input observed" if login else "Page screenshot; login form not observed") +
            ("; page rendering is incomplete because requests were blocked" if limited else "")})
    if login:
        asset["login_screenshot_path"] = output["screenshot_path"]
    records = [{"category": "web_endpoints", **asset}]
    if limited:
        records.append({"category": "scope_and_coverage", "feature": ctx.capability, "target": url, "status": "partial",
            "reason": "browser_requests_blocked", "blocked_requests": output["blocked_requests"],
            "blocked_details": output.get("blocked_details", []), "evidence_ids": [ctx.last_evidence_id]})
    return result(ctx, [asset], records, status="partial" if limited else "completed", reason="browser_requests_blocked" if limited else "")


def search(ctx):
    from .panel.fofa import Fofa
    from .panel.quake import Quake
    from .panel.hunter import Hunter
    from .panel.zoomeye import ZoomEye
    from .panel.shodan import Shodan
    from .panel.censys import Censys
    engines = {e.name: e for e in (Fofa, Quake, Hunter, ZoomEye, Shodan, Censys)}
    credentials = {"fofa": ["FOFA_EMAIL", "FOFA_KEY"], "quake": ["QUAKE_TOKEN"], "hunter": ["HUNTER_KEY"],
        "zoomeye": ["ZOOEYE_KEY"], "shodan": ["SHODAN_KEY"], "censys": ["CENSYS_ID", "CENSYS_SECRET"]}
    assets, records, failures = [], [], []
    requested = [ctx.step["tool"]]
    if requested[0] not in ctx.params.get("engines", list(engines)):
        return result(ctx, status="skipped", reason="selected_engine_not_in_parameters")
    # Credentials are backend-only and loaded only when executing an explicitly selected live index call.
    from dotenv import load_dotenv
    load_dotenv(ctx.workbench.root / ".env", override=False)
    for name in requested:
        if name not in engines or not all(os.getenv(key) for key in credentials[name]):
            failures.append(name + ":credentials_missing")
            continue
        ctx.require(ctx.target)
        engine = engines[name]
        host = ctx.target
        if _is_ip(host):
            query = f'ip="{host}"' if name == "fofa" else f'ip:"{host}"'
        elif "." in host or host == "localhost":
            query = Fofa.domain_query(host) if name == "fofa" else f'domain:"{host}"'
        else:
            # Do not fabricate company-query syntax unsupported by the selected engine.
            records.append({"category": "organizations_relationships", "name": host, "status": "blocked", "reason": "company_lookup_provider_required"})
            failures.append(name + ":subject_query_not_supported")
            continue
        try:
            with Database(ctx.workbench.root / "data/account-rate-ledger.sqlite") as db:
                account = digest([name, [os.getenv(k, "") for k in credentials[name]]])[:16]
                class AccountLimiter(RateLimiter):
                    def __init__(self):
                        rates = ctx.run["config"].get("rates", {})
                        super().__init__(db, name, min_interval=max(15, rates.get("fofa_min_interval", 15)) if name == "fofa" else rates.get(name + "_min_interval", 1),
                            daily=min(200, rates.get("fofa_daily", 200)) if name == "fofa" else rates.get(name + "_daily", 200), sleeper=ctx.wait)
                        self.source = name + ":" + account
                    def acquire(self):
                        ctx.require(ctx.target)
                        return super().acquire()
                limiter = AccountLimiter()
                panel = engine(db, ctx.run["config"], limiter=limiter)
                original_client_request = panel.client.request
                def checked_request(*args, **kwargs):
                    # Reservations/waits do not authorize the request after a revocation.
                    ctx.require(ctx.target)
                    return original_client_request(*args, **kwargs)
                panel.client.request = checked_request
                original_request = panel.request
                def traced_request(method, url, **kwargs):
                    public = {k: v for k, v in kwargs.get("params", {}).items() if k.lower() not in {"key", "api-key", "email", "token"}}
                    body = redacted_snapshot(kwargs.get("json", {}))
                    return ctx.call(name, {"endpoint": urlsplit(url).path, "query": query, "params": public, "body": body}, lambda: original_request(method, url, **kwargs))
                panel.request = traced_request
                try:
                    page_options = {"max_pages": int(ctx.params.get("max_pages_per_query", 2))} if name != "quake" else {"size": int(ctx.params.get("size", 100))}
                    iterator = panel.search(query, **page_options)
                    for item in iterator:
                        row = asdict(item)
                        row.update({"asset_id": digest([item.host, item.port, item.proto])[:24], "name": item.host,
                            "protocol": item.proto, "sources": [name], "verification_status": "candidate_only", "evidence_ids": [ctx.last_evidence_id], "observed_at": utcnow()})
                        assets.append(row)
                    if getattr(panel, "last_errors", []):
                        failures.append(name + ":source_degraded")
                    if getattr(panel, "health", None):
                        records.append({"category": "tool_health", "source": name, **panel.health})
                finally:
                    panel.close()
        except QuotaExceeded:
            failures.append(name + ":quota-exhausted")
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            from .orchestrator import RunControlled
            from .policy import PolicyDenied
            if isinstance(exc, (RunControlled, PolicyDenied)):
                raise
            failures.append(name + ":source_failed")
    status = "partial" if failures and assets else "blocked" if failures else "completed"
    return result(ctx, assets, records, status=status, reason=";".join(failures))


def passive_subdomains(ctx):
    if ctx.step["tool"] != "certificate_indexes":
        return result(ctx, status="blocked", reason="selected_passive_source_adapter_not_integrated")
    # Certificate transparency requests target a public index; no target resolver/HTTP request.
    ctx.require(ctx.target)
    def fetch():
        with httpx.Client(timeout=float(ctx.params.get("timeout_seconds", 30)), follow_redirects=False, trust_env=False) as client:
            reply = client.get("https://crt.sh/", params={"q": "%." + ctx.target, "output": "json"})
            reply.raise_for_status()
            return reply.json()
    payload = ctx.call("certificate_indexes", {"root": ctx.target, "index": "crt.sh"}, fetch)
    records, assets = [], []
    names = sorted({name.removeprefix("*.").strip().lower() for entry in payload for name in entry.get("name_value", "").splitlines()})
    for name in names:
        try:
            name = normalize_host(name)
        except ValueError:
            continue
        asset = {"asset_id": digest([name, "domain"])[:24], "asset_type": "domain", "name": name, "domain": name,
            "sources": ["crt.sh"], "verification_status": "candidate_only", "evidence_ids": [ctx.last_evidence_id], "confidence": "C"}
        assets.append(asset)
        records.append({"category": "domains", **asset})
    return result(ctx, assets, records)


def imported_source(ctx):
    files = ctx.params.get("evidence_files", [])
    if not files:
        return result(ctx, status="blocked", reason="configured_source_or_evidence_required")
    records = []
    for filename in files:
        path = (ctx.workbench.root / filename).resolve()
        if not path.is_relative_to(ctx.workbench.root) or not path.is_file() or any(p.startswith(".env") for p in path.parts):
            raise ValueError("Invalid evidence input")
        ctx.require(ctx.target, network=False)
        content = ctx.call("evidence_import", {"path": str(path.relative_to(ctx.workbench.root))}, lambda: json.loads(path.read_text(encoding="utf-8")))
        for row in content if isinstance(content, list) else [content]:
            records.append({"category": "organizations_relationships", **row, "evidence_ids": [ctx.last_evidence_id]})
    return result(ctx, records=records)


def tool_registry():
    from .active_tools import adapters
    from .passive_tools import adapters as passive_adapters
    from .passive_indexes import passive_subdomains as indexed_subdomains
    registry = {**adapters(), "search": search,
        "web_visit": web_visit, "screenshot": screenshot, "web_crawl": web_crawl,
        "js_analysis": js_analysis, "web_path_enum": web_paths, "exposure_check": exposure_check,
        "vulnerability_check": vulnerability_check, "takeover_probe": takeover_probe, "auth_audit": auth_audit,
        **passive_adapters(), "passive_subdomains": indexed_subdomains}
    from .external_tools import route
    return {capability: route(capability, adapter) for capability, adapter in registry.items()}

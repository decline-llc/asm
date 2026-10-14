"""WSL adapters sharing policy, durable receipts, evidence and report contracts.

HTTP tools have no direct target transport: they execute in a private network
namespace and broker every request to ExecutionContext.http. Unsupported
protocols, methods and template types never get an upstream transport.
"""
import base64
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import queue
import re
import shlex
import subprocess
import threading
import time
from urllib.parse import urlsplit
import uuid

import yaml

from .bridge import Bridge, BridgeError, WsFs, decode
from .policy import PolicyDenied
from .run_store import digest
from .scope import normalize_host
from .utils.dns import parse_dig, parse_endpoint, record_value

HTTP_TOOLS = frozenset({"httpx", "ffuf", "katana", "gowitness", "wafw00f", "nuclei"})
SUPPORTED = {
    "tcp_scan": {"naabu", "a_scan"}, "dns_recursive": {"dnsx", "dig_probe"},
    "web_visit": {"httpx"}, "web_path_enum": {"ffuf"}, "web_crawl": {"katana"},
    "screenshot": {"gowitness"}, "vulnerability_check": {"nuclei", "wafw00f"},
}
SECLISTS = {
    "seclists:dns_top5000": "Discovery/DNS/subdomains-top1million-5000.txt",
    "seclists:web_directories": "Discovery/Web-Content/raft-medium-directories.txt",
    "seclists:web_files": "Discovery/Web-Content/raft-medium-files.txt",
    "seclists:web_words": "Discovery/Web-Content/raft-medium-words.txt",
    "seclists:web_extensions": "Discovery/Web-Content/raft-medium-extensions.txt",
}


def _result(ctx, assets=None, records=None, status="completed", reason=""):
    return {"status": status, "reason": reason, "assets": assets or [], "records": (records or []) + getattr(ctx, "records", [])}


def _bridge(ctx):
    return getattr(ctx, "bridge", None) or Bridge()


def _job(ctx, files):
    bridge = _bridge(ctx)
    directory = bridge.workspace + "/results/workbench-" + uuid.uuid4().hex
    fs = WsFs(bridge)
    ctx.require(ctx.target)
    fs.mkdir(directory)
    for name, content in files.items():
        if Path(name).name != name or name.startswith("."):
            raise ValueError("Invalid tool job input filename")
        fs.write_bytes(directory + "/" + name, content.encode("utf-8") if isinstance(content, str) else content)
    return bridge, fs, directory


def frozen_dictionary(ctx, value, default):
    """Freeze local/locked SecLists input in the run receipt, including on resume."""
    if value == "built_in_basic":
        return list(default)
    if isinstance(value, list):
        return list(value)
    if not isinstance(value, str):
        raise ValueError("Invalid dictionary selection")
    def load():
        if value in SECLISTS:
            bridge = _bridge(ctx)
            repository = bridge.workspace + "/wordlists/SecLists"
            path = repository + "/" + SECLISTS[value]
            source = Path(__file__).resolve().parents[1]
            expected = json.loads((source / "tools/tool-lock.json").read_text(encoding="utf-8"))["source_repositories"]["SecLists"]["commit"]
            actual = decode(bridge.control(shlex.join(["git", "-C", repository, "rev-parse", "HEAD"])).stdout).strip()
            if actual != expected:
                raise ValueError("SecLists installation does not match the tool lock")
            installed_blob = decode(bridge.control(shlex.join(["git", "-C", repository, "hash-object", path])).stdout).strip()
            locked_blob = decode(bridge.control(shlex.join(["git", "-C", repository, "rev-parse", "HEAD:" + SECLISTS[value]])).stdout).strip()
            if installed_blob != locked_blob:
                raise ValueError("SecLists dictionary has been changed")
            raw = decode(bridge.control("head -c 10485761 -- " + shlex.quote(path)).stdout).encode("utf-8")
        else:
            path = (ctx.workbench.root / value).resolve()
            if not path.is_relative_to(ctx.workbench.root.resolve()) or any(p.startswith(".env") for p in path.parts) or not path.is_file():
                raise ValueError("Dictionary must be a project file or a known SecLists resource")
            with path.open("rb") as stream:
                raw = stream.read(10485761)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Dictionary exceeds 10 MiB")
        return {"resource": value, "sha256": hashlib.sha256(raw).hexdigest(), "entries": list(dict.fromkeys(x.strip() for x in raw.decode("utf-8").splitlines() if x.strip()))}
    return ctx.call(ctx.step["tool"], {"operation": "dictionary_input", "resource": value}, load)["entries"]


def port_scan(ctx):
    from .active_tools import _literal_target, _ports, _run_scanner
    target, ports, tool = _literal_target(ctx), _ports(ctx), ctx.step["tool"]
    if not ports:
        return _result(ctx, status="skipped", reason="empty_explicit_ports")
    if ctx.capability != "tcp_scan":
        return _result(ctx, status="blocked", reason="tool_supports_tcp_discovery_only")
    rate = float(ctx.params.get("packets_per_second", 100))
    if not 0 < rate <= 100000:
        raise ValueError("Invalid port rate")
    size = ctx.params.get("batch_size", 512)
    if type(size) is not int or not 1 <= size <= 4096:
        raise ValueError("Invalid batch_size")
    batches = [ports[i:i + size] for i in range(0, len(ports), size)] if ctx.params.get("split_batches", False) else [ports]
    assets, records = [], []
    for batch in batches:
        if tool == "naabu":
            if rate < 1:
                return _result(ctx, status="blocked", reason="naabu_requires_integer_rate_at_least_one")
            args = ["-host", target, "-p", ",".join(map(str, batch)), "-s", "c", "-rate", str(math.floor(rate)), "-retries", "0", "-j", "-silent", "-duc", "-Pn"]
            executable = "naabu"
        else:
            source = Path(__file__).resolve().parents[1] / "tools/scanners/a_scan.py"
            code = source.read_bytes()
            args = ["--host", target, "--ports", ",".join(map(str, batch)), "--threads", "1", "--timeout", str(ctx.params.get("timeout_seconds", 1)), "--rate", str(rate)]
            def run_local_copy():
                _, _, directory = _job(ctx, {"a_scan.py": code})
                return _run_scanner(ctx, [directory + "/a_scan.py", *args], executable="python3", cwd=directory)
        params = {"target": target, "args": args}
        if tool == "a_scan":
            params["script_sha256"] = hashlib.sha256(code).hexdigest()
        raw = ctx.call(tool, params, run_local_copy if tool == "a_scan" else lambda: _run_scanner(ctx, args, executable=executable))
        records.append({"category": "service_observations", "tool": tool, "covered_ports": batch, "evidence_ids": [ctx.last_evidence_id]})
        if raw.get("exit_code") != 0:
            return _result(ctx, assets, records, "partial" if assets else "blocked" if raw.get("availability") == "unavailable" else "failed", "external_port_tool_failed")
        for line in raw["stdout"].splitlines():
            row = json.loads(line)
            host, port = row.get("ip", row.get("host")), int(row["port"])
            if host != target or port not in batch or row.get("protocol", row.get("proto", "tcp")) != "tcp":
                raise ValueError("Unexpected scanner output target/port/protocol")
            assets.append({"host": target, "ip": target, "port": port, "proto": "tcp", "source": tool,
                           "verification_status": "observed", "attribution_status": "unconfirmed", "evidence_ids": [ctx.last_evidence_id]})
    return _result(ctx, assets, records)


def dns_query(ctx, domain, rtype, resolver, gate=None):
    from .active_tools import _run_scanner
    host, port = parse_endpoint(resolver)
    ctx.require(domain)
    if gate:
        gate.start(ctx, domain)
    timeout = float(ctx.params.get("timeout_seconds", 3))
    tool = ctx.step["tool"]
    if tool == "dig_probe":
        args = ["@" + host, "-p", str(port), domain + ".", rtype, "+noall", "+answer", "+comments", "+tries=1", "+time=" + str(math.ceil(timeout))]
        raw = _run_scanner(ctx, args, executable="dig")
        parsed = parse_dig(raw.get("stdout", ""))
    else:
        # One name, record type and explicit upstream per durable action.
        args = ["-l", domain, "-" + rtype.lower(), "-r", resolver, "-retry", "1", "-t", "1", "-rl", "1", "-timeout", str(timeout) + "s", "-j", "-silent", "-nc", "-duc"]
        raw = _run_scanner(ctx, args, executable="dnsx")
        parsed = {"status": "NOANSWER", "answers": []}
        for line in raw.get("stdout", "").splitlines():
            row = json.loads(line)
            if normalize_host(row.get("host", "")) != domain:
                raise ValueError("Unexpected DNS output host")
            parsed["status"] = row.get("status_code", "NOERROR")
            parsed["answers"].extend({"name": domain, "rtype": rtype, "value": value} for value in row.get(rtype.lower(), []))
    values = []
    for item in parsed["answers"]:
        value, accepted, rejection = item["value"], True, ""
        try:
            value = record_value(item["rtype"], value, reject_fake_ip=ctx.params.get("reject_fake_ip", True))
        except ValueError as exc:
            accepted, rejection = False, str(exc)
        values.append({**item, "value": value, "accepted": accepted, "rejection": rejection})
    return {"domain": domain, "query_type": rtype, "resolver": resolver, "status": parsed["status"] if raw.get("exit_code") == 0 else "DEPENDENCY_UNAVAILABLE" if raw.get("availability") == "unavailable" else "ERROR", "answers": values, "tool_output": raw}


def oneforall(ctx):
    from .active_tools import _run_scanner
    from .utils.oneforall import OneForAllSettings, PASSIVE_FLAGS, domain_name
    root = domain_name(ctx.target)
    configured = dict(ctx.run["config"].get("oneforall", {}))
    configured.update({key: ctx.params[key] for key in ("modules", "module_timeout", "request_timeout") if key in ctx.params})
    settings = OneForAllSettings.from_config({"oneforall": configured})
    bridge = _bridge(ctx)
    source = Path(__file__).resolve().parents[1]
    lock = json.loads((source / "tools/tool-lock.json").read_text(encoding="utf-8"))
    plan = {"root": root, "settings": settings.as_config(), "vendor": bridge.workspace + "/tools/OneForAll", "expected_commit": lock["source_repositories"]["OneForAll"]["commit"]}
    def collect():
        _, fs, directory = _job(ctx, {"oneforall_runner.py": (source / "tools/oneforall_runner.py").read_bytes(),
                                     "oneforall_support.py": (source / "asm/utils/oneforall.py").read_bytes(), "input.json": json.dumps(plan)})
        result = _run_scanner(ctx, [directory + "/oneforall_runner.py", "--input", directory + "/input.json"], executable=plan["vendor"] + "/.venv/bin/python", cwd=directory)
        if result.get("availability") == "unavailable":
            return result
        report = json.loads(fs.read_text(directory + "/oneforall-run.json"))
        if report.get("root") != root or report.get("mode") != "passive" or report.get("flags") != dict.fromkeys(PASSIVE_FLAGS, False):
            raise ValueError("Collector does not prove the frozen passive-only contract")
        observations = json.loads(fs.read_text(directory + "/oneforall-observations.json")) if fs.exists(directory + "/oneforall-observations.json") else []
        return {**result, "report": report, "rows": observations}
    raw = ctx.call("oneforall_passive", {"operation": "isolated_live_job", "root": root, "modules": list(settings.modules), "flags": dict.fromkeys(PASSIVE_FLAGS, False), "commit": plan["expected_commit"]}, collect)
    if raw.get("availability") == "unavailable":
        return _result(ctx, status="blocked", reason="oneforall_wsl_dependency_unavailable")
    if raw["report"].get("flags") != dict.fromkeys(PASSIVE_FLAGS, False):
        raise ValueError("Saved collector receipt has invalid passive flags")
    assets = []
    for row in raw["rows"]:
        if not isinstance(row, dict) or not row.get("subdomain"):
            continue
        host = domain_name(row["subdomain"].removeprefix("*."))
        if host != root and not host.endswith("." + root):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(row.get("source", ""))):
            raise ValueError("Unexpected collector source")
        assets.append({"name": host, "domain": host, "asset_type": "domain", "sources": ["oneforall:" + str(row.get("source", "unknown"))],
                       "verification_status": "candidate_only", "attribution_status": "unconfirmed", "evidence_ids": [ctx.last_evidence_id]})
    return _result(ctx, assets, [{"category": "tool_health", "source": "oneforall_passive", "live_execution": True, "status": raw["report"]["status"]}], "completed" if raw["report"]["status"] == "completed" else "partial", "" if raw["report"]["status"] == "completed" else "collector_source_errors")


def approved_templates(ctx):
    values = ctx.params.get("approved_templates", [])
    if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
        raise ValueError("approved_templates must contain project YAML filenames")
    templates = {}
    for index, value in enumerate(values):
        path = (ctx.workbench.root / value).resolve()
        if not path.is_relative_to(ctx.workbench.root.resolve()) or not path.is_file() or path.suffix not in {".yaml", ".yml"} or path.stat().st_size > 1024 * 1024:
            raise ValueError("Invalid approved template file")
        text = path.read_text(encoding="utf-8")
        template = yaml.safe_load(text)
        if not isinstance(template, dict) or set(template) - {"id", "info", "http", "variables"} or not template.get("http"):
            raise ValueError("Only explicit HTTP observation templates are supported")
        for request in template["http"]:
            if not isinstance(request, dict) or request.get("method", "GET") not in {"GET", "HEAD"} or any(k in request for k in ("raw", "body", "payloads", "fuzzing", "unsafe", "race", "pipeline", "redirects")):
                raise ValueError("Template requires unsupported request behavior")
        templates["template-" + str(index) + ".yaml"] = text
    return templates


def _receive_frames(stream, messages):
    try:
        while True:
            line = stream.readline(48 * 1024 * 1024 + 1)
            if not line:
                break
            if len(line) > 48 * 1024 * 1024:
                raise ValueError("Tool frame exceeds byte limit")
            messages.put(json.loads(line))
    except BaseException as exc:
        messages.put(exc)
    finally:
        messages.put(None)


def _http_job(ctx, spec, files):
    source = Path(__file__).resolve().parents[1]
    bridge, _, directory = _job(ctx, {**files, "spec.json": json.dumps(spec), "http_tool_runner.py": (source / "tools/http_tool_runner.py").read_bytes()})
    script = "ip link set lo up && exec python3 " + shlex.quote(directory + "/http_tool_runner.py") + " " + shlex.quote(directory + "/spec.json")
    command = bridge.command("unshare", ["--user", "--map-root-user", "--net", "bash", "-c", script], timeout=spec["job_timeout"] + 10)
    pid = directory + "/process-group.pid"
    launcher = "setsid --fork --wait bash -c " + shlex.quote("echo $$ > " + shlex.quote(pid) + "; " + command)
    messages, artifacts, requests, errors = queue.Queue(), {}, [], []
    process = None
    stderr_path = Path(ctx.output_directory) / (uuid.uuid4().hex + ".broker.stderr")
    try:
        with stderr_path.open("wb") as stderr:
            process = subprocess.Popen(bridge.argv(launcher, cwd=directory), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
            threading.Thread(target=_receive_frames, args=(process.stdout, messages), daemon=True).start()
            deadline, total, completed = time.monotonic() + spec["job_timeout"] + 20, 0, None
            while True:
                ctx.require(ctx.target)
                if time.monotonic() >= deadline:
                    raise TimeoutError("HTTP tool broker exceeded job deadline")
                try:
                    frame = messages.get(timeout=0.1)
                except queue.Empty:
                    continue
                if frame is None:
                    break
                if isinstance(frame, BaseException):
                    raise frame
                if frame["kind"] == "started":
                    ctx.records.append({"category": "execution_steps", "step_id": ctx.step["id"], "feature": ctx.capability, "tool": spec["tool"], "version": frame["version"], "params": frame["args"], "status": "running"})
                elif frame["kind"] == "http_request":
                    url, method = frame["url"], frame["method"]
                    if method not in {"GET", "HEAD"} or urlsplit(url).scheme not in {"http", "https"}:
                        raise ValueError("Unsupported broker request")
                    try:
                        # Every tool-generated URL, redirect and subresource enters
                        # the same current policy, receipts and physical ledger.
                        reply = ctx.http(url, method=method, request_headers=frame.get("headers"), max_response_bytes=int(ctx.params.get("max_response_bytes", 4 * 1024 * 1024)), follow_redirects=False)
                        requests.append({"url": url, "status": reply["status"], "evidence_id": ctx.last_evidence_id})
                    except PolicyDenied as exc:
                        if "outside" not in str(exc):
                            raise
                        errors.append({"url": url, "reason": "outside_function_scope"})
                        reply = {"status": 403, "headers": {}, "body_base64": ""}
                    process.stdin.write((json.dumps({"id": frame["id"], "status": reply["status"], "headers": reply["headers"], "body_base64": reply.get("body_base64", base64.b64encode(reply.get("body", "").encode()).decode())}) + "\n").encode())
                    process.stdin.flush()
                elif frame["kind"] == "artifact":
                    name = frame["name"]
                    if not re.fullmatch(r"(?:tool\.(?:stdout|stderr)|result\.jsonl?|screenshots/[A-Za-z0-9._-]+\.png)", name):
                        raise ValueError("Unexpected tool artifact path")
                    content = base64.b64decode(frame["body_base64"], validate=True)
                    if name.startswith("screenshots/") and not content.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("Screenshot artifact is not a PNG")
                    total += len(content)
                    if total > 32 * 1024 * 1024:
                        raise ValueError("Tool artifact byte budget exceeded")
                    path = Path(ctx.output_directory) / ("external-" + spec["tool"]) / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        raise ValueError("Tool evidence must not overwrite an existing file")
                    path.write_bytes(content)
                    ctx._evidence(uuid.uuid4().hex, path, "external_tool_output")
                    artifacts[name] = path.relative_to(ctx.run["directory"]).as_posix()
                elif frame["kind"] == "completed":
                    completed = frame
                else:
                    raise ValueError("Unknown tool protocol event")
            code = process.wait(timeout=5)
            return {"exit_code": completed["exit_code"] if completed else code or 1, "artifacts": artifacts, "requests": requests, "scope_blocks": errors, "transport": "isolated_http_broker", "protocol_completed": bool(completed), "args": completed.get("args", []) if completed else [], "version": completed.get("version", "") if completed else ""}
    except (BridgeError, FileNotFoundError) as exc:
        return {"exit_code": None, "availability": "unavailable", "error": type(exc).__name__, "artifacts": artifacts, "requests": requests}
    finally:
        if process is not None and process.poll() is None:
            try:
                bridge.control("if test -f " + shlex.quote(pid) + "; then kill -TERM -- -$(cat " + shlex.quote(pid) + ") 2>/dev/null; fi", timeout=5, check=False)
            except BridgeError:
                pass
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        if stderr_path.is_file():
            ctx._evidence(uuid.uuid4().hex, stderr_path, "external_tool_broker_log")


def http_tool(ctx):
    tool = ctx.step["tool"]
    parsed = urlsplit(ctx.target)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTP tools require an explicit HTTP(S) URL")
    timeout = int(ctx.params.get("timeout_seconds", 60 if tool == "gowitness" else 15))
    rate = float(ctx.params.get("requests_per_second", 2))
    if not 1 <= timeout <= 300 or not 0 < rate <= 100000:
        raise ValueError("Invalid HTTP tool timeout/rate")
    if tool == "katana":
        ctx.params["max_requests_per_host"] = min(int(ctx.params.get("max_requests_per_host", 200)), int(ctx.params.get("max_urls_per_host", 200)))
    else:
        ctx.params.setdefault("max_requests_per_host", 1000)
    if tool == "wafw00f" and "waf_fingerprint" not in ctx.params.get("approved_checks", []):
        return _result(ctx, status="skipped", reason="waf_fingerprint_check_not_selected")
    files = {"urls.txt": ctx.target + "\n"}
    if tool == "nuclei":
        files.update(approved_templates(ctx))
        if not files.keys() - {"urls.txt"}:
            return _result(ctx, status="skipped", reason="empty_approved_templates")
    if tool == "ffuf":
        from .workbench_tools import PATHS
        words = frozen_dictionary(ctx, ctx.params.get("dictionary", "built_in_basic"), [p.lstrip("/") for p in PATHS])
        if any(not isinstance(w, str) or not w or w.startswith(("/", "\\")) or "\n" in w or "\r" in w for w in words):
            raise ValueError("Invalid Web dictionary entry")
        words = words[:int(ctx.params.get("max_requests_per_host", 1000))]
        files["dictionary.txt"] = "\n".join(words) + "\n"
        baseline = ctx.http(ctx.target.rstrip("/") + "/asm-missing-" + digest(ctx.step["id"])[:24])
    else:
        baseline = None
    spec = {"tool": tool, "target": ctx.target, "host": parsed.hostname, "rate": max(1, math.floor(rate)), "timeout": timeout,
            "job_timeout": int(ctx.params.get("host_timeout_seconds", 180)), "depth": int(ctx.params.get("max_depth", 2)),
            "max_requests_per_host": ctx.params["max_requests_per_host"],
            "crawl_scope": "^" + re.escape(parsed.scheme + "://" + parsed.netloc) + r"(?:/|$)", "templates": [n for n in files if n.startswith("template-")]}
    if tool == "gowitness":
        spec["driver"] = ctx.params.get("driver", "gorod")
        if spec["driver"] not in {"chromedp", "gorod"}:
            raise ValueError("Invalid gowitness browser driver")
    raw = ctx.call(tool, {"operation": "isolated_http_job", "spec": spec, "input_sha256": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, lambda: _http_job(ctx, spec, files))
    return parse_http_result(ctx, raw, baseline)


def parse_http_result(ctx, raw, baseline=None):
    tool = ctx.step["tool"]
    if raw.get("availability") == "unavailable":
        return _result(ctx, status="blocked", reason="http_tool_wsl_dependency_unavailable")
    records = [{"category": "tool_health", "source": tool, "exit_code": raw["exit_code"], "transport": raw.get("transport"), "scope_blocks": raw.get("scope_blocks", []), "evidence_ids": [ctx.last_evidence_id]}]
    rows = []
    for name in ("result.json", "result.jsonl", "tool.stdout"):
        relative = raw.get("artifacts", {}).get(name)
        if not relative:
            continue
        text = (Path(ctx.run["directory"]) / relative).read_text(encoding="utf-8")
        if name == "result.json":
            data = json.loads(text)
            rows = data.get("results", []) if isinstance(data, dict) else data
            break
        if name == "result.jsonl" or tool in {"httpx", "katana", "nuclei"}:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            break
    requests = {r["url"]: r for r in raw.get("requests", [])}
    assets = []
    screenshot_complete = tool != "gowitness"
    for row in rows:
        url = row.get("url", row.get("matched-at", row.get("request", {}).get("endpoint", ctx.target)))
        if url not in requests:
            records.append({"category": "out_of_scope_leads", "url": url, "source": tool, "reason": "tool_output_not_observed_by_broker"})
            continue
        ctx.require(url, network=False)
        evidence = [requests[url]["evidence_id"], ctx.last_evidence_id]
        if tool in {"nuclei", "wafw00f"}:
            if tool == "wafw00f" and not row.get("detected"):
                records.append({"category": "web_observations", "url": url, "source": tool, "waf_detected": False, "evidence_ids": evidence})
                continue
            records.append({"category": "findings", "finding_id": digest([tool, url, row])[:24], "kind": "template_candidate" if tool == "nuclei" else "waf_fingerprint", "url": url, "title": row.get("info", {}).get("name", row.get("detected", "WAF fingerprint")), "status": "review", "basis": row, "evidence_ids": evidence})
            continue
        if tool == "ffuf" and baseline is not None:
            # A candidate is confirmed through the existing governed HTTP path.
            reply = ctx.http(url)
            if reply["status"] == 404 or (reply["status"], digest(reply["body"])) == (baseline["status"], digest(baseline["body"])):
                continue
            evidence.append(ctx.last_evidence_id)
        parsed = urlsplit(url)
        address = parsed.hostname if _is_ip(parsed.hostname) else ""
        asset = {"asset_type": "web_endpoint", "name": parsed.hostname, "domain": "" if address else parsed.hostname,
                 "ip": address, "port": parsed.port or (443 if parsed.scheme == "https" else 80), "url": url,
                 "http_status": row.get("status_code", row.get("status", requests[url]["status"])), "title": row.get("title", ""),
                 "technology": ",".join(row.get("tech", [])) if isinstance(row.get("tech"), list) else row.get("tech", ""), "sources": [tool], "verification_status": "observed", "attribution_status": "unconfirmed", "evidence_ids": evidence}
        if tool == "gowitness":
            images = [path for name, path in raw["artifacts"].items() if name.startswith("screenshots/")]
            if len(images) == 1 and not row.get("failed"):
                asset["screenshot_path"] = images[0]
                screenshot_complete = True
            else:
                records.append({"category": "web_observations", "url": url, "source": tool,
                                "screenshot_complete": False, "reason": row.get("failed_reason", "screenshot_artifact_missing"), "evidence_ids": evidence})
                continue
        assets.append(asset)
        records.append({"category": "web_endpoints", **asset})
    status = "completed" if raw["exit_code"] == 0 and raw.get("protocol_completed") and requests and screenshot_complete else "partial" if requests else "failed"
    records.append({"category": "execution_steps", "step_id": ctx.step["id"], "feature": ctx.capability, "tool": tool, "version": raw.get("version", ""), "params": raw.get("args", []), "status": status, "outputs": list(raw.get("artifacts", {}).values()), "evidence_ids": [ctx.last_evidence_id]})
    return _result(ctx, assets, records, status, "" if status == "completed" else "external_http_tool_failed")


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False


def route(capability, fallback):
    def execute(ctx):
        tool = ctx.step["tool"]
        live_collector = capability == "passive_subdomains" and tool == "oneforall_passive" and not (ctx.params.get("oneforall_report") or ctx.params.get("oneforall_observations"))
        if live_collector or tool in SUPPORTED.get(capability, set()):
            from .preflight import dependency_status
            dependencies = dependency_status(ctx.run["config"], capability, tool)
            if dependencies["status"] == "blocked":
                return _result(ctx, status="blocked", reason=dependencies["reason"])
        if live_collector:
            return oneforall(ctx)
        if tool in HTTP_TOOLS and tool in SUPPORTED.get(capability, set()):
            return http_tool(ctx)
        return fallback(ctx)
    return execute

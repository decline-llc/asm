"""Workbench company, public-code and relationship adapters.

Company providers currently require an operator's saved export. The existing
field/ICP/SSE/tender parsers are reused, while their legacy stage runners are
deliberately avoided because they bundle unrelated target requests or ledgers.
Public-code collection uses the explicitly selected Sourcegraph index. Supply
analysis reads the current run's saved facts and never probes a discovered lead.
"""
from __future__ import annotations

import codecs
import hashlib
import ipaddress
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .browser.aiqicha import parse_seven_fields
from .db import Database
from .models import utcnow
from .panel.base import QuotaExceeded, RateLimiter
from .parallel.p1_osint import parse_sse, parse_tender, validate_keyword
from .policy import redacted_snapshot
from .run_store import digest
from .scope import normalize_host
from .stages.s2b_icp import branch, enumerate_subnumbers, parse_icp

SOURCEGRAPH_URL = "https://sourcegraph.com/.api/search/stream"
COMPANY_TOOLS = {"stage_2a", "stage_2b", "company_evidence_import"}
OSINT_TOOLS = {"stage_p1", "sourcegraph_stream", "tender_import", "osint_evidence_import"}
SUPPLY_TOOLS = {"stage_p2", "saved_supply_analysis"}
EQUITY_FIELDS = {"cid", "name", "company", "parent_cid", "share_pct", "website", "email_suffix", "domains", "ips", "observed_at"}
SUPPLY_FIELDS = {"category", "organization", "related_organization", "company", "relationship", "domains", "domain",
                "website", "ip", "sans", "certificate", "observed_at", "vendor", "system_name", "deployment", "lead_category"}


def _result(ctx, assets=None, records=None, *, status="completed", reason=""):
    canonical = {}
    for row in assets or []:
        key = row["asset_id"]
        if key not in canonical:
            canonical[key] = dict(row)
            continue
        existing = canonical[key]
        for field in ("evidence_ids", "sources"):
            existing[field] = sorted(set(existing.get(field, [])) | set(row.get(field, [])))
        if existing.get("knowledge") == "inference" and row.get("knowledge") == "observation":
            existing.update(knowledge="observation", confidence=row.get("confidence", "C"))
        if not existing.get("url") and row.get("url"):
            existing["url"] = row["url"]
    return {"status": status, "reason": reason, "assets": list(canonical.values()), "records": (records or []) + list(ctx.records)}


def _tool(ctx):
    return ctx.step["tool"]


def _seed_kind(ctx):
    if ctx.capability == "company_lookup":
        return "subject"
    scope_ref = ctx.policy.check(ctx.capability, ctx.target, network=False).scope_ref
    for kind in ("subject", "query", "brand"):
        if ctx.policy.contains(scope_ref, ctx.target, target_kind=kind):
            return kind
    try:
        normalize_host(ctx.target)
        return "host"
    except ValueError:
        return "query"


def _require(ctx, *, network=False):
    return ctx.require(ctx.target, target_kind=_seed_kind(ctx), network=network)


def _replay(ctx):
    return ctx.run["config"].get("execution", {}).get("source") == "replay"


def _values(value, name):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise ValueError(name + " must contain nonempty strings")
    return list(dict.fromkeys(value))


def _files(ctx, name, legacy_section=None):
    values = _values(ctx.params.get(name), name)
    if legacy_section:
        values += _values(ctx.run["config"].get(legacy_section, {}).get("import_file"), legacy_section + ".import_file")
    return list(dict.fromkeys(values))


def _mapping_rows(document):
    rows = document.get("records", document.get("companies", [document])) if isinstance(document, dict) else document
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Evidence export must contain a list of mappings")
    return rows


def _safe_fields(row, allowed):
    return redacted_snapshot({key: value for key, value in row.items() if key in allowed})


def _import(ctx, filename, kind, parser):
    _require(ctx)
    root = Path(ctx.workbench.root).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root) or any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Evidence input must stay inside the workspace and cannot be a secret file")
    relative = path.relative_to(root).as_posix()

    def read():
        ctx.check_control()
        maximum = int(ctx.params.get("max_input_bytes", 5 * 1024 * 1024))
        if maximum <= 0:
            raise ValueError("max_input_bytes must be positive")
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise ValueError("Evidence export exceeds max_input_bytes")
        ctx.check_control()
        value = parser(raw.decode("utf-8-sig"))
        return {"source_kind": kind, "source_path": relative, "source_sha256": hashlib.sha256(raw).hexdigest(),
                "source_bytes": len(raw), "content_policy": "parsed_fields_only", "parsed": value}

    captured = ctx.call(_tool(ctx), {"operation": "saved_evidence_import", "kind": kind, "path": relative}, read)
    return captured["parsed"], ctx.last_evidence_id, captured


def _asset(value, source, evidence_ids, relationship, *, inferred=False):
    value = redacted_snapshot(value)
    if not isinstance(value, str) or not value or value.startswith("[REDACTED"):
        return None
    try:
        host = normalize_host(value.removeprefix("*."))
        parsed = urlsplit(value) if "://" in value else None
        if parsed and parsed.scheme not in {"http", "https"}:
            return None
        address = str(ipaddress.ip_address(host))
    except ValueError:
        try:
            host = normalize_host(value.removeprefix("*."))
        except ValueError:
            return None
        address = ""
        parsed = urlsplit(value) if "://" in value else None
    row = {"asset_id": "passive-" + digest([host, parsed.port if parsed else None, "passive_lead"])[:24],
           "asset_type": "ip" if address else "domain", "name": host, "domain": "" if address else host, "ip": address,
           "url": value if parsed else "", "sources": [source], "verification_status": "candidate_only",
           "attribution_status": "unconfirmed", "confidence": "D" if inferred else "C",
           "knowledge": "inference" if inferred else "observation", "relationship": relationship,
           "evidence_ids": sorted(set(evidence_ids)), "observed_at": utcnow(), "execution_source": "live",
           "remarks": "Saved/public-source lead; ownership and service availability are unverified"}
    if parsed:
        row["port"] = parsed.port or (443 if parsed.scheme == "https" else 80)
        row["protocol"] = parsed.scheme
    return row


def _append_leads(assets, records, row, values, source, evidence_ids, relationship, *, inferred=False):
    for value in values:
        asset = _asset(value, source, evidence_ids, relationship, inferred=inferred)
        if asset is None:
            continue
        asset["organization"] = row.get("name") or row.get("company") or row.get("organization", "")
        asset["lead_category"] = row.get("lead_category") or ("group" if "equity" in relationship else "ip" if asset["ip"] else "unclassified")
        assets.append(asset)
        records.append({"category": "domains" if asset["domain"] else "ip_services", **asset})


def _equity_export(text):
    rows = _mapping_rows(json.loads(text))
    output = []
    for row in rows:
        parsed = _safe_fields(row, EQUITY_FIELDS)
        if parsed.get("share_pct") is not None:
            percentage = float(parsed["share_pct"])
            if not math.isfinite(percentage) or not 0 <= percentage <= 100:
                raise ValueError("Saved equity percentages must be finite values between 0 and 100")
            parsed["share_pct"] = percentage
        output.append(parsed)
    return output


def _icp_export(text):
    output = []
    for row in _mapping_rows(json.loads(text)):
        saved_text = str(row.get("text", ""))
        numbers = parse_icp(saved_text)
        for number in _values(row.get("icp_numbers", row.get("icp_number")), "icp_numbers"):
            numbers.extend(parse_icp(number))
        output.append({**_safe_fields(row, {"domain", "related_domains", "organization", "company", "observed_at", "status"}),
                       "numbers": sorted(set(numbers)), "number_groups": enumerate_subnumbers(numbers),
                       "saved_response_branch": branch(row.get("status"), saved_text)})
    return output


def _company_fields(text):
    parsed = parse_seven_fields(text)
    return {key: value for key, value in parsed.items() if key in {"company", "capital", "legal_person", "founded", "address"}}


def company_lookup(ctx):
    if _replay(ctx):
        return _result(ctx, status="blocked", reason="replay_uses_saved_replay_adapter")
    if _tool(ctx) not in COMPANY_TOOLS:
        return _result(ctx, status="blocked", reason="selected_company_provider_not_integrated")
    if ctx.params.get("affiliation_evidence_required", True) is not True:
        raise ValueError("Company affiliation evidence is mandatory")
    if type(ctx.params.get("include_controlled_entities", True)) is not bool:
        raise ValueError("include_controlled_entities must be boolean")
    _require(ctx)
    equity_files = _files(ctx, "equity_files", "equity") if _tool(ctx) != "stage_2b" else []
    icp_files = _files(ctx, "icp_files", "icp") if _tool(ctx) != "stage_2a" else []
    if _tool(ctx) == "stage_2a":
        equity_files += _files(ctx, "evidence_files")
    elif _tool(ctx) == "stage_2b":
        icp_files += _files(ctx, "evidence_files")
    profile_files = _files(ctx, "company_profile_files") if _tool(ctx) != "stage_2b" else []
    if not equity_files and not icp_files and not profile_files:
        return _result(ctx, status="blocked", reason="manual_company_equity_or_icp_export_required_no_autonomous_provider_configured")
    assets, records = [], []
    threshold = float(ctx.params.get("min_control_share_pct", 51))
    if not math.isfinite(threshold) or not 0 < threshold <= 100:
        raise ValueError("min_control_share_pct must be between 0 and 100")
    for filename in dict.fromkeys(equity_files):
        rows, evidence_id, metadata = _import(ctx, filename, "equity", _equity_export)
        maximum = int(ctx.params.get("max_records", 2000))
        if len(rows) > maximum:
            raise ValueError("Equity export exceeds max_records")
        keyed = {}
        for row in rows:
            ctx.check_control()
            key = str(row.get("cid") or digest([row.get("name"), row.get("parent_cid")])[:24])
            if key in keyed and keyed[key] != row:
                raise ValueError("Conflicting organization identifiers in saved equity export")
            keyed[key] = dict(row, cid=key)
        accepted = {key for key, row in keyed.items() if not row.get("parent_cid") and
                    " ".join(str(row.get("name", row.get("company", ""))).casefold().split()) == " ".join(ctx.target.casefold().split())}
        for _ in range(len(keyed)):
            before = set(accepted)
            if ctx.params.get("include_controlled_entities", True):
                for key, row in keyed.items():
                    share = float(row.get("share_pct") or 0)
                    if math.isfinite(share) and 0 <= share <= 100 and str(row.get("parent_cid")) in accepted and share >= threshold:
                        accepted.add(key)
            if accepted == before:
                break
            ctx.check_control()
        for key, row in keyed.items():
            ctx.check_control()
            parent = row.get("parent_cid")
            linked = key in accepted
            relationship = "equity_control_candidate" if parent and linked else "equity_interest_observed" if parent else "organization_export_observation"
            record = {"category": "organizations_relationships", "organization_id": key,
                      "organization": row.get("name") or row.get("company", ""), "related_organization": str(parent or ""),
                      "relationship": relationship, "attribution_status": "unconfirmed", "status": "candidate",
                      "knowledge": "inference" if parent and linked else "observation", "observed_share_pct": row.get("share_pct"),
                      "website": row.get("website"), "domains": row.get("domains", []), "email_suffix": row.get("email_suffix"),
                      "ips": row.get("ips", []),
                      "basis": {"source_sha256": metadata["source_sha256"], "requested_subject_control_path": linked,
                                "control_threshold_pct": threshold}, "source": "operator_equity_export",
                      "observed_at": row.get("observed_at"), "evidence_ids": [evidence_id]}
            records.append(record)
            if linked:
                values = _values(row.get("website"), "website") + _values(row.get("email_suffix"), "email_suffix")
                values += _values(row.get("domains"), "domains") + _values(row.get("ips"), "ips")
                _append_leads(assets, records, row, values, "operator_equity_export", [evidence_id], relationship)
    for filename in dict.fromkeys(icp_files):
        rows, evidence_id, metadata = _import(ctx, filename, "icp", _icp_export)
        for row in rows:
            ctx.check_control()
            records.append({"category": "organizations_relationships", "organization": row.get("organization") or row.get("company") or "",
                "related_organization": row.get("domain", ""), "relationship": "saved_icp_association", "knowledge": "observation",
                "attribution_status": "unconfirmed", "status": "candidate", "numbers": row["numbers"],
                "domain": row.get("domain"), "domains": row.get("related_domains", []), "requested_subject": ctx.target,
                "number_groups": row["number_groups"], "saved_response_branch": row["saved_response_branch"],
                "basis": {"source_sha256": metadata["source_sha256"]}, "evidence_ids": [evidence_id], "source": "operator_icp_export",
                "observed_at": row.get("observed_at")})
            values = _values(row.get("domain"), "domain") + _values(row.get("related_domains"), "related_domains")
            _append_leads(assets, records, row, values, "operator_icp_export", [evidence_id], "saved_icp_association")
    for filename in dict.fromkeys(profile_files):
        parsed, evidence_id, metadata = _import(ctx, filename, "company_fields", _company_fields)
        records.append({"category": "organizations_relationships", "organization": parsed.get("company") or "", "requested_subject": ctx.target,
            "relationship": "company_profile_export", "knowledge": "observation", "attribution_status": "unconfirmed",
            "status": "candidate" if any(parsed.values()) else "no_results", "profile": parsed,
            "source_sha256": metadata["source_sha256"], "evidence_ids": [evidence_id]})
    return _result(ctx, assets, records, reason="operator_exports_parsed_no_target_requests_no_ownership_verification")


def _sse_metadata(lines, maximum):
    locations, done = [], False
    for event, payload in parse_sse(lines):
        if event == "matches" and isinstance(payload, list):
            for match in payload:
                if not isinstance(match, dict):
                    continue
                row = _safe_fields(match, {"type", "repository", "path", "url", "commit"})
                if row.get("repository") or row.get("path"):
                    locations.append(row)
                if len(locations) >= maximum:
                    return {"locations": locations, "done": done, "truncated": True, "snippet_policy": "omitted"}
        elif event == "progress" and isinstance(payload, dict):
            done = payload.get("done") is True
    return {"locations": locations, "done": done, "truncated": False, "snippet_policy": "omitted"}


def _keyword(ctx, value):
    value = validate_keyword(value)
    if "@" in value:
        scoped, kind = value.rsplit("@", 1)[1], "host"
    else:
        try:
            scoped, kind = normalize_host(value), "host"
        except ValueError:
            scoped, kind = value, "subject"
        scope_ref = ctx.policy.check(ctx.capability, ctx.target, network=False).scope_ref
        for typed_kind in ("subject", "query", "brand"):
            if ctx.policy.contains(scope_ref, value, target_kind=typed_kind):
                scoped, kind = value, typed_kind
                break
    ctx.require(scoped, target_kind=kind, network=True)
    return value, scoped, kind


def _sourcegraph(ctx, keyword, maximum):
    keyword, scoped, kind = _keyword(ctx, keyword)
    query = f'context:global "{keyword}" (password OR secret OR config) count:{maximum}'

    def fetch():
        with Database(Path(ctx.workbench.root) / "data/account-rate-ledger.sqlite") as db:
            rates = ctx.run["config"].get("rates", {})
            limiter = RateLimiter(db, "sourcegraph:public", min_interval=1 / max(float(ctx.params.get("requests_per_second", 1)), 0.01),
                                  daily=int(rates.get("sourcegraph_daily", 200)), sleeper=ctx.wait)
            limiter.acquire()
            ctx.require(scoped, target_kind=kind, network=True)
            with httpx.Client(timeout=float(ctx.params.get("timeout_seconds", 45)), follow_redirects=False, trust_env=False) as client:
                with client.stream("GET", SOURCEGRAPH_URL, params={"q": query, "v": "V3"}, headers={"Accept": "text/event-stream"}) as reply:
                    reply.raise_for_status()
                    count, truncated, source_hash = 0, False, hashlib.sha256()
                    byte_limit = int(ctx.params.get("max_response_bytes", 1024 * 1024))
                    decoder, buffer = codecs.getincrementaldecoder("utf-8")("replace"), ""

                    def lines():
                        nonlocal count, truncated, buffer
                        for chunk in reply.iter_bytes():
                            ctx.check_control()
                            if count + len(chunk) > byte_limit:
                                chunk, truncated = chunk[:max(0, byte_limit - count)], True
                            count += len(chunk)
                            source_hash.update(chunk)
                            buffer += decoder.decode(chunk)
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                yield line
                            if truncated:
                                break
                        buffer += decoder.decode(b"", final=True)
                        if buffer:
                            yield buffer
                        yield ""

                    metadata = _sse_metadata(lines(), maximum)
                    return {**metadata, "truncated": metadata["truncated"] or truncated, "source_sha256": source_hash.hexdigest(),
                            "source_bytes": count, "hash_coverage": "received_prefix", "http_status": reply.status_code}

    data = ctx.call(_tool(ctx), {"provider": "sourcegraph", "endpoint": SOURCEGRAPH_URL, "query": query, "max_results": maximum}, fetch)
    return data, ctx.last_evidence_id


def osint(ctx):
    if _replay(ctx):
        return _result(ctx, status="blocked", reason="replay_uses_saved_replay_adapter")
    if _tool(ctx) not in OSINT_TOOLS:
        return _result(ctx, status="blocked", reason="selected_osint_provider_not_integrated")
    if ctx.params.get("evidence_required", True) is not True:
        raise ValueError("OSINT source evidence is mandatory")
    _require(ctx)
    source_defaults = {"sourcegraph_stream": ["sourcegraph"], "tender_import": ["tender_files"],
                       "osint_evidence_import": ["sse_files", "tender_files"]}
    sources = _values(ctx.params.get("sources", source_defaults.get(_tool(ctx), [])), "sources")
    if _tool(ctx) == "stage_p1" and not sources:
        sources = [name for name in ("sse_files", "tender_files") if ctx.params.get(name) or ctx.run["config"].get("osint", {}).get(name)]
    if set(sources) - {"sourcegraph", "sse_files", "tender_files"}:
        raise ValueError("Unknown OSINT source selection")
    allowed_by_tool = {"sourcegraph_stream": {"sourcegraph"}, "tender_import": {"tender_files"},
                       "osint_evidence_import": {"sse_files", "tender_files"}}
    if _tool(ctx) in allowed_by_tool and set(sources) - allowed_by_tool[_tool(ctx)]:
        raise ValueError("OSINT source does not match the selected tool")
    if not sources:
        return _result(ctx, status="blocked", reason="explicit_osint_sources_or_saved_exports_required")
    maximum = int(ctx.params.get("max_results_per_source", 100))
    if maximum <= 0:
        raise ValueError("max_results_per_source must be positive")
    assets, records, covered, partial, failures = [], [], 0, False, []
    for source in sources:
        if source == "sourcegraph":
            keywords = _values(ctx.params.get("keywords", ctx.run["config"].get("osint", {}).get("keywords", [ctx.target])), "keywords")
            for keyword in keywords:
                try:
                    data, evidence_id = _sourcegraph(ctx, keyword, maximum)
                except (httpx.HTTPError, QuotaExceeded) as exc:
                    failures.append("sourcegraph:" + type(exc).__name__)
                    records.append({"category": "tool_health", "source": "sourcegraph", "status": "quota-exhausted" if isinstance(exc, QuotaExceeded) else "failed",
                                    "reason": type(exc).__name__, "evidence_ids": [ctx.last_evidence_id] if ctx.last_evidence_id else []})
                    continue
                covered += 1
                source_partial = data["truncated"] or not data["done"]
                partial |= source_partial
                records.append({"category": "tool_health", "source": "sourcegraph", "status": "partial" if source_partial else "completed",
                    "result_count": len(data["locations"]), "truncated": data["truncated"], "stream_done": data["done"], "evidence_ids": [evidence_id]})
                for location in data["locations"]:
                    records.append({"category": "findings", "kind": "public_code_reference", "title": "Public source keyword reference",
                        "severity": "info", "status": "review", "knowledge": "candidate", "keyword": keyword, "location": location,
                        "basis": "Location metadata only; source snippets and credential values omitted", "evidence_ids": [evidence_id]})
        elif source == "sse_files":
            filenames = _files(ctx, source) or _values(ctx.run["config"].get("osint", {}).get(source), source)
            if not filenames:
                failures.append("sse_files:no_configured_input")
                records.append({"category": "tool_health", "source": source, "status": "blocked", "reason": "no_configured_input"})
            for filename in filenames:
                data, evidence_id, _ = _import(ctx, filename, "sourcegraph_sse", lambda text: _sse_metadata(text.splitlines(), maximum))
                covered += 1
                source_partial = data["truncated"] or not data["done"]
                partial |= source_partial
                records.append({"category": "tool_health", "source": "saved_sourcegraph_sse", "status": "partial" if source_partial else "completed",
                    "result_count": len(data["locations"]), "truncated": data["truncated"], "stream_done": data["done"], "evidence_ids": [evidence_id]})
                for location in data["locations"]:
                    records.append({"category": "findings", "kind": "saved_public_code_reference", "title": "Saved public source reference",
                        "severity": "info", "status": "review", "knowledge": "candidate", "location": location, "evidence_ids": [evidence_id]})
        else:
            filenames = _files(ctx, source) or _values(ctx.run["config"].get("osint", {}).get(source), source)
            if not filenames:
                failures.append("tender_files:no_configured_input")
                records.append({"category": "tool_health", "source": source, "status": "blocked", "reason": "no_configured_input"})
            for filename in filenames:
                data, evidence_id, metadata = _import(ctx, filename, "tender", parse_tender)
                covered += 1
                records.append({"category": "tool_health", "source": "saved_tender_export", "status": "completed",
                                "parsed_fields": sum(value is not None for value in data.values()), "evidence_ids": [evidence_id]})
                records.append({"category": "organizations_relationships", "organization": ctx.target, "related_organization": data.get("vendor"),
                    "relationship": "supplier_claimed_in_saved_tender", "status": "candidate", "knowledge": "observation",
                    "attribution_status": "unconfirmed", "tender": data, "source_sha256": metadata["source_sha256"], "evidence_ids": [evidence_id]})
                values = _values(data.get("deployment"), "deployment") + _values(data.get("ip"), "ip")
                _append_leads(assets, records, data, values, "operator_tender_export", [evidence_id], "saved_tender_deployment")
    return _result(ctx, assets, records, status="blocked" if not covered else "partial" if partial or failures else "completed",
                   reason=";".join(failures) if failures else "selected_source_files_missing" if not covered else "public_source_metadata_and_unverified_leads")


def _certificate_hosts(row):
    values = row.get("sans", [])
    values = list(values) if isinstance(values, list) else str(values).splitlines()
    cert = row.get("certificate", {})
    if isinstance(cert, dict):
        values += [pair[1] for pair in cert.get("subjectAltName", []) if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] in {"DNS", "IP Address"}]
    return values


def _supply_export(text):
    return [_safe_fields(row, SUPPLY_FIELDS) for row in _mapping_rows(json.loads(text))]


def passive_supply_chain(ctx):
    if _replay(ctx):
        return _result(ctx, status="blocked", reason="replay_uses_saved_replay_adapter")
    if _tool(ctx) not in SUPPLY_TOOLS:
        return _result(ctx, status="blocked", reason="selected_supply_analysis_not_integrated")
    _require(ctx)
    if ctx.params.get("inferred_scope_auto_add", False):
        raise ValueError("Inferred relationships cannot automatically expand scope")
    dimensions = _values(ctx.params.get("dimensions", ["certificates", "organizations", "tenders", "vendors", "neighbor_ips"]), "dimensions")
    if set(dimensions) - {"certificates", "organizations", "tenders", "vendors", "neighbor_ips"}:
        raise ValueError("Unknown supply-chain dimension")
    current = ctx.workbench.run(ctx.run["run_id"])
    saved = [json.loads(r["data"]) for r in ctx.workbench.store.rows("SELECT data FROM records WHERE run=?", (ctx.run["run_id"],))]
    for filename in _files(ctx, "evidence_files"):
        rows, evidence_id, _ = _import(ctx, filename, "supply_relationships", _supply_export)
        saved.extend({**row, "evidence_ids": [evidence_id]} for row in rows)

    def analyze():
        candidates, relations = [], []
        certificate_limit = int(ctx.params.get("certificate_domain_limit", 8))
        neighbor_limit = int(ctx.params.get("neighbor_ip_limit", 6))
        if certificate_limit < 0 or neighbor_limit < 0:
            raise ValueError("Supply lead limits cannot be negative")
        host_budget = int(ctx.run["config"].get("budgets", {}).get("max_hosts", 1000))
        certificate_limit, neighbor_limit = min(certificate_limit, host_budget), min(neighbor_limit, host_budget)
        seen_certificates, seen_neighbors = set(), set()
        for row in saved:
            ctx.check_control()
            ids = row.get("evidence_ids", [])
            if "certificates" in dimensions:
                for host in _certificate_hosts(row):
                    asset = _asset(host, "saved_certificate_analysis", ids, "certificate_cooccurrence", inferred=True)
                    if asset and asset["name"] not in seen_certificates and len(seen_certificates) < certificate_limit:
                        seen_certificates.add(asset["name"])
                        candidates.append(asset)
            if "organizations" in dimensions and row.get("category") == "organizations_relationships":
                relations.append({"organization": row.get("organization"), "related_organization": row.get("related_organization"),
                    "relationship": row.get("relationship", "saved_organization_relation"), "status": "candidate", "knowledge": "inference",
                    "attribution_status": "unconfirmed", "evidence_ids": ids})
                values = _values(row.get("domains"), "domains") + _values(row.get("website"), "website")
                values += _values(row.get("domain"), "domain") + _values(row.get("email_suffix"), "email_suffix") + _values(row.get("ips"), "ips")
                for value in values:
                    asset = _asset(value, "saved_organization_analysis", ids, "organization_domain_candidate", inferred=True)
                    if asset:
                        asset["organization"] = row.get("organization", row.get("company", ""))
                        asset["lead_category"] = "vendor" if row.get("vendor") else "group" if row.get("relationship", "").startswith("equity") else row.get("lead_category", "unclassified")
                        candidates.append(asset)
            if "tenders" in dimensions and isinstance(row.get("tender"), dict):
                tender = row["tender"]
                relations.append({"organization": row.get("organization"), "related_organization": tender.get("vendor"),
                    "relationship": "saved_tender_supplier_candidate", "status": "candidate", "knowledge": "inference",
                    "attribution_status": "unconfirmed", "evidence_ids": ids})
        if "vendors" in dimensions:
            vendors = _values(ctx.params.get("vendor_list", ctx.run["config"].get("supply_chain", {}).get("vendor_list", [])), "vendor_list")
            relations.extend({"organization": ctx.target, "related_organization": vendor, "relationship": "operator_supplier_review_card",
                              "status": "candidate", "knowledge": "operator_declaration", "attribution_status": "unconfirmed", "evidence_ids": []} for vendor in vendors)
        if "neighbor_ips" in dimensions:
            for row in current["assets"]:
                ctx.check_control()
                for value in str(row.get("ip", "")).splitlines():
                    try:
                        address = ipaddress.ip_address(value)
                    except ValueError:
                        continue
                    network = ipaddress.ip_network(str(address) + ("/24" if address.version == 4 else "/64"), strict=False)
                    for offset in range(1, neighbor_limit + 1):
                        neighbor = int(address) + offset
                        if neighbor > int(network.broadcast_address) or len(seen_neighbors) >= neighbor_limit:
                            break
                        host = str(type(address)(neighbor))
                        if host in seen_neighbors:
                            continue
                        seen_neighbors.add(host)
                        asset = _asset(host, "saved_neighbor_inference", row.get("evidence_ids", []), "adjacent_address_candidate", inferred=True)
                        if asset:
                            asset["lead_category"] = "ip"
                            candidates.append(asset)
        return {"dimensions": dimensions, "assets": candidates, "relationships": relations,
                "source_asset_ids": [row["asset_id"] for row in current["assets"]],
                "source_evidence_ids": sorted({eid for row in saved for eid in row.get("evidence_ids", [])}),
                "network_requests": 0, "scope_auto_added": False, "ownership_verified": False}

    data = ctx.call(_tool(ctx), {"operation": "saved_supply_analysis", "seed": ctx.target, "dimensions": dimensions,
                               "certificate_domain_limit": ctx.params.get("certificate_domain_limit", 8),
                               "neighbor_ip_limit": ctx.params.get("neighbor_ip_limit", 6)}, analyze)
    evidence_id, assets, records = ctx.last_evidence_id, data["assets"], []
    for asset in assets:
        asset["evidence_ids"] = sorted(set(asset["evidence_ids"]) | {evidence_id})
        host = asset["domain"] or asset["ip"]
        scoped = ctx.policy.contains("investigation", host)
        records.append({"category": "domains" if scoped and asset["domain"] else "ip_services" if scoped else "out_of_scope_leads",
            **asset, "scope_status": "in_scope" if scoped else "out_of_scope",
            "next_step": "Review relationship; manually add investigation scope before further collection"})
    for relation in data["relationships"]:
        records.append({"category": "organizations_relationships", **relation,
                        "evidence_ids": sorted(set(relation["evidence_ids"]) | {evidence_id})})
    records.append({"category": "tool_health", "source": "saved_supply_analysis", "status": "completed", "dimensions": dimensions,
                    "network_requests": 0, "scope_auto_added": False, "ownership_verified": False, "evidence_ids": [evidence_id]})
    return _result(ctx, assets, records, reason="saved_evidence_relationship_inference_only_no_live_certificate_queries")


def adapters():
    return {"company_lookup": company_lookup, "osint": osint, "passive_supply_chain": passive_supply_chain}

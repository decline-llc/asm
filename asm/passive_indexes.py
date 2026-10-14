"""Independent public-index and passive collector steps; no target DNS/Web."""
import json
from urllib.parse import urlsplit

import httpx

from .run_store import digest
from .scope import normalize_host, is_local
from .utils.oneforall import PASSIVE_FLAGS


def _result(ctx, assets=None, records=None, status="completed", reason=""):
    return {"status": status, "reason": reason, "assets": assets or [], "records": (records or []) + ctx.records}


def _public_index(ctx, endpoint, params):
    ctx.require(ctx.target)
    def request():
        ctx.require(ctx.target)
        with httpx.Client(timeout=float(ctx.params.get("timeout_seconds", 30)), trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", endpoint, params=params) as response:
                response.raise_for_status()
                raw = bytearray()
                maximum = int(ctx.params.get("max_response_bytes", 8 * 1024 * 1024))
                for chunk in response.iter_bytes(chunk_size=16384):
                    ctx.check_control()
                    raw.extend(chunk[:maximum - len(raw)])
                    if len(raw) >= maximum:
                        raise ValueError("Public index response exceeds configured byte budget")
                return json.loads(raw)
    return ctx.call(ctx.step["tool"], {"index": urlsplit(endpoint).hostname, "params": params}, request)


def passive_subdomains(ctx):
    if ctx.run["config"]["execution"]["source"] != "live":
        return _result(ctx, status="skipped", reason="replay_has_no_live_index_fallback")
    tool, root = ctx.step["tool"], normalize_host(ctx.target)
    if is_local(root):
        return _result(ctx, status="skipped", reason="local_seed_has_no_public_index_collection")
    names, records = [], []
    if tool == "certificate_indexes":
        raw = _public_index(ctx, "https://crt.sh/", {"q": "%." + root, "output": "json"})
        if not isinstance(raw, list):
            return _result(ctx, status="partial", reason="invalid_certificate_index_response")
        for row in raw:
            if isinstance(row, dict):
                names.extend(str(row.get("name_value", "")).splitlines())
        source = "crt.sh"
    elif tool == "archive_indexes":
        maximum = int(ctx.params.get("max_results_per_source", 1000))
        raw = _public_index(ctx, "https://web.archive.org/cdx/search/cdx", {"url": "*." + root + "/*", "output": "json", "collapse": "urlkey", "filter": "statuscode:200", "limit": maximum})
        if raw:
            try:
                column = raw[0].index("original")
                names.extend(urlsplit(row[column]).hostname for row in raw[1:])
            except (ValueError, TypeError, IndexError):
                return _result(ctx, status="partial", reason="invalid_archive_index_response")
        source = "web.archive.org"
    elif tool == "subfinder":
        from .active_tools import _run_scanner
        args = ["-d", root, "-silent", "-duc"]
        raw = ctx.call(tool, {"domain": root, "args": args, "mode": "passive"}, lambda: _run_scanner(ctx, args))
        if raw.get("availability") == "unavailable" or raw.get("exit_code") not in {0}:
            return _result(ctx, status="blocked", reason="selected_passive_collector_unavailable_or_failed")
        names.extend(raw["stdout"].splitlines())
        source = "subfinder"
    elif tool == "oneforall_passive":
        # The pinned legacy runner is isolated. Its verified exported output can
        # be ingested without re-running modules or restoring a legacy live job.
        filenames = [ctx.params.get("oneforall_report"), ctx.params.get("oneforall_observations")]
        if not all(filenames):
            return _result(ctx, status="blocked", reason="isolated_oneforall_workbench_job_adapter_pending_or_saved_exports_required")
        def read():
            values = []
            for name in filenames:
                path = (ctx.workbench.root / name).resolve()
                if not path.is_relative_to(ctx.workbench.root) or not path.is_file() or any(p.startswith(".env") for p in path.parts):
                    raise ValueError("Invalid saved collector evidence")
                values.append(json.loads(path.read_text(encoding="utf-8-sig")))
            report, rows = values
            if report.get("root") != root or report.get("mode") != "passive" or set(report.get("flags", {})) != set(PASSIVE_FLAGS) or any(v is not False for v in report["flags"].values()):
                raise ValueError("Saved collector report does not prove passive flags")
            if not isinstance(rows, list):
                raise ValueError("Saved collector observations must be a list")
            return {"report": report, "rows": rows}
        raw = ctx.call(tool, {"saved_exports": filenames, "mode": "saved_evidence"}, read)
        names.extend(row.get("subdomain") for row in raw["rows"] if isinstance(row, dict))
        source = "oneforall_saved_evidence"
        records.append({"category": "tool_health", "source": source, "status": raw["report"].get("status", "unknown"), "live_execution": False})
    else:
        return _result(ctx, status="blocked", reason="selected_passive_source_not_integrated")
    assets = []
    limit = int(ctx.params.get("max_results_per_source", 1000))
    accepted = set()
    for name in names:
        if not isinstance(name, str):
            continue
        try:
            host = normalize_host(name.removeprefix("*."))
        except ValueError:
            continue
        if host in accepted or len(accepted) >= limit:
            continue
        accepted.add(host)
        assets.append({"asset_id": digest([host, "domain"])[:24], "asset_type": "domain", "name": host,
            "domain": host, "sources": [source], "verification_status": "candidate_only", "attribution_status": "unconfirmed",
            "evidence_ids": [ctx.last_evidence_id], "knowledge": "candidate"})
    records.extend({"category": "domains", **row} for row in assets)
    return _result(ctx, assets, records)

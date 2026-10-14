"""Workbench replay imports saved evidence; no transport or live-tool fallback."""
import copy
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .models import utcnow
from .run_store import digest
from .scope import normalize_host


SECRET_KEYS = re.compile(r"^(?:api[_-]?key|key|token|access[_-]?token|password|secret|email|fofa[_-]?email|fofa[_-]?key|authorization|proxy-authorization|cookie|set-cookie)$", re.I)
SECRET_ASSIGNMENT = re.compile(r"(?i)([?&](?:api_key|apikey|key|token|access_token|password|secret|email)=)[^&\s\"'<>]+")


def _redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEYS.fullmatch(str(key)) else _redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", value)
    return value


def _safe_path(root, value):
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Replay inputs must stay in the project and cannot be secret files")
    return path


def _bytes_for_export(path):
    raw = path.read_bytes()
    if path.suffix.lower() not in {".json", ".jsonl", ".txt", ".log", ".html", ".md", ".csv"}:
        return raw, raw
    try:
        text = raw.decode("utf-8-sig")
        if path.suffix.lower() == ".json":
            value = json.loads(text)
            cleaned = _redact(value)
            if cleaned != value:
                return raw, json.dumps(cleaned, ensure_ascii=False, indent=2).encode("utf-8")
        elif path.suffix.lower() == ".jsonl":
            lines = [json.loads(line) for line in text.splitlines() if line.strip()]
            cleaned = _redact(lines)
            if cleaned != lines:
                return raw, ("\n".join(json.dumps(line, ensure_ascii=False) for line in cleaned) + "\n").encode("utf-8")
        cleaned = _redact(text)
        return raw, cleaned.encode("utf-8") if cleaned != text else raw
    except ValueError:
        cleaned = _redact(text)
        return raw, cleaned.encode("utf-8") if cleaned != text else raw
    except UnicodeError:
        return raw, raw


class EvidenceImporter:
    def __init__(self, ctx):
        self.ctx = ctx
        self.root = Path(ctx.workbench.root).resolve()
        self.directory = _safe_path(self.root, ctx.run["directory"])
        self.files = {}
        self.records = []
        self.issues = []

    def capture(self, path):
        if hasattr(self.ctx, "check_control"):
            self.ctx.check_control()
        path = _safe_path(self.root, path)
        source = path.relative_to(self.root).as_posix()
        if source in self.files:
            return self.files[source]
        if not path.is_file():
            self.issues.append({"source": source, "status": "missing_evidence"})
            return None
        original, saved = _bytes_for_export(path)
        original_hash = hashlib.sha256(original).hexdigest()
        saved_hash = hashlib.sha256(saved).hexdigest()
        suffix = path.suffix.lower() if re.fullmatch(r"\.[a-z0-9]{1,10}", path.suffix.lower()) else ".bin"
        relative = "evidence/" + saved_hash + suffix
        destination = self.directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != saved:
                raise ValueError("Existing immutable replay evidence differs from its content hash")
        else:
            with destination.open("xb") as stream:
                stream.write(saved)
        identifier = "replay-evidence-" + digest([source, original_hash])[:24]
        row = {"record_id": identifier, "evidence_id": identifier, "category": "evidence_index",
            "path": relative, "original_path": source, "source": "saved_evidence",
            "sha256": saved_hash, "source_sha256": original_hash, "bytes": len(saved),
            "source_bytes": len(original), "source_mtime": datetime.fromtimestamp(path.stat().st_mtime,
                timezone.utc).isoformat(), "execution_source": "replay", "replayed_at": utcnow(),
            "redacted": original != saved}
        self.files[source] = row
        self.records.append(row)
        store = getattr(self.ctx.workbench, "store", None)
        if store is not None and hasattr(store, "connection"):
            with store.connection() as conn:
                cursor = conn.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?)",
                    (identifier, self.ctx.run["run_id"], "evidence_index", json.dumps(row, ensure_ascii=False)))
                if cursor.rowcount:
                    store.event(self.ctx.run["run_id"], "artifact_written", row, conn)
        return row

    def resolve_output(self, package, value):
        if not isinstance(value, str):
            return None
        for base in (package, self.root):
            try:
                path = _safe_path(base, value)
                if path.is_file() and path.is_relative_to(package):
                    return path
            except ValueError:
                continue
        return None


def classify_historical_status(raw):
    """Classify readable evidence, without trying to repair corrupt status text."""
    text = str(raw or "")
    lower = text.lower()
    if "820000" in text or any(word in lower for word in ("failed", "error", "denied", "failure")):
        return "failed"
    if "429" in text or any(word in lower for word in ("degraded", "partial", "rate-limit", "quota")):
        return "degraded"
    if "\ufffd" in text:
        return "unknown"
    if lower in {"success", "succeeded", "completed", "ok", "200", "成功"}:
        return "completed"
    if lower in {"stopped", "interrupted", "cancelled", "canceled"}:
        return "interrupted"
    return "unknown"


def _already_recorded(ctx, replay_key):
    store = getattr(ctx.workbench, "store", None)
    if store is None or not hasattr(store, "events"):
        return False
    for event in store.events(ctx.run["run_id"]):
        data = event.get("data", {})
        provenance = data.get("provenance", {}) if isinstance(data, dict) else {}
        if event.get("kind") == "tool_call" and isinstance(provenance, dict) and provenance.get("replay_key") == replay_key:
            return True
    return False


def _record(ctx, key, tool, params, outputs, provenance):
    if hasattr(ctx, "check_control"):
        ctx.check_control()
    provenance = {**provenance, "replay_key": key, "execution_source": "replay", "new_network_requests": 0}
    if not _already_recorded(ctx, key):
        ctx.record(tool, _redact(params), "replayed", outputs, _redact(provenance))


def _normal_asset(row, index, source, observed_at, evidence_ids, importer, package):
    row = _redact(copy.deepcopy(row))
    url = row.get("url") or row.get("link") or ""
    url = url.splitlines()[0].strip() if isinstance(url, str) and url else ""
    parsed = urlsplit(url) if "://" in url else None
    host = row.get("domain") or (parsed.hostname if parsed else None) or row.get("host") or row.get("name") or ""
    host_mapping = None
    if row.get("kind") == "dns-only" and not row.get("domain") and not row.get("host") and not (parsed and parsed.hostname):
        # The saved seven-column contract decorates a literal observed DNS name.
        # Remove only its known terminal annotation; arbitrary display text stays
        # unparseable and cannot expand investigation scope through a fuzzy match.
        for annotation in ("（仅 DNS）", "(DNS-only)"):
            if isinstance(host, str) and host.endswith(annotation):
                literal = host.removesuffix(annotation).strip()
                try:
                    host = normalize_host(literal)
                except ValueError:
                    break
                host_mapping = {"field": "name", "annotation": annotation, "status": "parsed_saved_literal"}
                break
    try:
        port = row.get("port") or (parsed.port if parsed else None)
    except ValueError:
        port = None
    addresses = []
    for item in re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|(?<!\w)[0-9a-fA-F]*:[0-9a-fA-F:]+(?!\w)",
                           str(row.get("ip_resolution") or row.get("ip") or "")):
        try:
            addresses.append(str(ipaddress.ip_address(item)))
        except ValueError:
            continue
    identifier = row.get("asset_id") or "replay-asset-" + digest([source, index, row.get("name"), url])[:24]
    kind = row.get("kind", "")
    state = "dns_only" if kind == "dns-only" else row.get("verification_status", "candidate_only")
    if state not in {"candidate_only", "dns_only", "replayed_verified", "quarantined"}:
        state = "candidate_only"
    asset = {**row, "asset_id": identifier, "name": row.get("name") or host, "domain": host,
        "ip": "\n".join(dict.fromkeys(addresses)), "url": url, "port": port,
        "protocol": row.get("protocol") or (parsed.scheme if parsed else ""),
        "http_status": row.get("http_status", row.get("status_code")),
        "title": row.get("title", ""), "verification_status": state,
        "attribution_status": row.get("attribution_status", "unconfirmed"),
        "sources": row.get("sources") if isinstance(row.get("sources"), list) else ["saved_evidence"],
        "observed_at": row.get("observed_at") or observed_at, "execution_source": "replay",
        "evidence_ids": sorted(set(row.get("evidence_ids", [])) | set(evidence_ids)),
        "source_record": {"path": source, "index": index}, "screenshot_path": ""}
    if host_mapping:
        asset["source_record"]["host_mapping"] = host_mapping
    screenshot = row.get("screenshot_path") or row.get("screenshot_rel") or row.get("screenshot_abs")
    if screenshot:
        path = importer.resolve_output(package, screenshot)
        saved = importer.capture(path) if path else None
        if saved and path.suffix.lower() == ".png":
            asset["screenshot_path"] = saved["path"]
            asset["screenshot_evidence_id"] = saved["evidence_id"]
            asset["evidence_ids"] = sorted(set(asset["evidence_ids"]) | {saved["evidence_id"]})
        else:
            importer.issues.append({"source": str(screenshot), "status": "missing_screenshot"})
    return asset


def _package(ctx, importer, package):
    observed = package / "target_observations.json"
    calls_path = package / "logs/tool-calls.jsonl"
    if not observed.is_file():
        return {"status": "blocked", "reason": "missing_target_observations", "assets": [], "records": []}
    dataset = json.loads(observed.read_text(encoding="utf-8-sig"))
    rows = dataset.get("observations", dataset.get("assets", [])) if isinstance(dataset, dict) else dataset
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Saved observations must be a list of records")
    source = observed.relative_to(importer.root).as_posix()
    saved_observations = importer.capture(observed)
    if (package / "evidence").is_dir():
        for path in sorted((package / "evidence").rglob("*")):
            if path.is_file():
                importer.capture(path)
    calls = []
    records = []
    if calls_path.is_file():
        importer.capture(calls_path)
        for line, raw in enumerate(calls_path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                call = json.loads(raw)
                if not isinstance(call, dict):
                    raise ValueError("Tool trace row is not a mapping")
            except ValueError:
                importer.issues.append({"source": str(calls_path.relative_to(importer.root)),
                    "line": line, "status": "invalid_trace_record"})
                continue
            raw_status = call.get("status", "")
            classification = classify_historical_status(raw_status)
            outputs, output_ids, unresolved = [], [], []
            for value in call.get("outputs", []):
                path = importer.resolve_output(package, value)
                saved = importer.capture(path) if path else None
                if saved:
                    outputs.append(saved["path"])
                    output_ids.append(saved["evidence_id"])
                else:
                    unresolved.append(_redact(value))
                    importer.issues.append({"source": _redact(value), "status": "unresolved_source_output"})
            key = digest([str(calls_path.relative_to(importer.root)), line, hashlib.sha256(raw.encode()).hexdigest()])
            provenance = {"source_path": str(calls_path.relative_to(importer.root)), "source_line": line,
                "observed_at": call.get("ts"), "source_status": raw_status,
                "status_class": classification, "source_provenance": call.get("provenance"),
                "source_note": call.get("note"), "source_outputs": call.get("outputs", []),
                "unresolved_source_outputs": unresolved, "evidence_ids": output_ids}
            _record(ctx, key, call.get("tool", "saved_tool_call"), call.get("params", {}), outputs, provenance)
            calls.append(classification)
            records.append({"record_id": "replay-call-" + key[:24], "category": "tool_health",
                "tool": call.get("tool", "saved_tool_call"), "status": classification,
                "source_status": raw_status, "params": _redact(call.get("params", {})),
                "outputs": outputs, "evidence_ids": output_ids, "observed_at": call.get("ts"),
                "execution_source": "replay", "source_record": provenance})
    else:
        importer.issues.append({"source": str(calls_path.relative_to(importer.root)), "status": "missing_tool_trace"})
    observed_at = dataset.get("generated_utc") if isinstance(dataset, dict) else None
    assets = [_normal_asset(row, index, source, observed_at, [saved_observations["evidence_id"]], importer, package)
              for index, row in enumerate(rows)]
    for asset in assets:
        records.append({"record_id": "replay-observation-" + asset["asset_id"],
            "category": "domains" if asset["verification_status"] == "dns_only" else "web_endpoints",
            "asset_id": asset["asset_id"], "domain": asset["domain"], "url": asset["url"],
            "verification_status": asset["verification_status"], "observed_at": asset["observed_at"],
            "source": "saved_evidence", "execution_source": "replay", "evidence_ids": asset["evidence_ids"]})
    bad = any(status != "completed" for status in calls) or bool(importer.issues)
    records.append({"record_id": "replay-package-" + digest(source)[:24], "category": "replay_summary",
        "source": source, "asset_count": len(assets), "source_tool_calls": len(calls),
        "historical_status_counts": {status: calls.count(status) for status in sorted(set(calls))},
        "issues": importer.issues, "observed_at": observed_at, "execution_source": "replay",
        "new_network_requests": 0, "new_quota_usage": 0})
    return {"status": "partial" if bad else "completed",
        "reason": "saved_evidence_imported_with_historical_or_missing_evidence_issues" if bad else "saved_evidence_imported",
        "assets": assets, "records": importer.records + _redact(records)}


def _fixture(ctx, importer):
    configured = ctx.run["config"].get("execution", {}).get("fixture_file", "tests/fixtures/workbench-replay.json")
    path = _safe_path(importer.root, configured)
    if not path.is_file():
        return {"status": "blocked", "reason": "missing_replay_fixture", "assets": [], "records": []}
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = document.get("capabilities", {}).get(ctx.step["capability"], [])
    if isinstance(entries, dict):
        entries = [entries]
    matching = [entry for entry in entries if isinstance(entry, dict) and entry.get("target") == ctx.step["target"]]
    if not matching:
        return {"status": "blocked", "reason": "no_matching_saved_capability_evidence", "assets": [], "records": []}
    saved = importer.capture(path)
    records, assets = [], []
    statuses = []
    for index, entry in enumerate(matching):
        state = classify_historical_status(entry.get("status", ""))
        outputs = [saved["path"]]
        ids = [saved["evidence_id"]]
        for reference in entry.get("evidence", []):
            captured = importer.capture(_safe_path(importer.root, reference))
            if captured:
                outputs.append(captured["path"])
                ids.append(captured["evidence_id"])
        source = path.relative_to(importer.root).as_posix()
        key = digest([source, saved["source_sha256"], ctx.step["capability"], ctx.step["target"], index])
        _record(ctx, key, entry.get("tool", "saved_fixture"), ctx.step.get("params", {}), outputs,
            {"source_path": source, "source_status": entry.get("status"), "status_class": state,
             "dataset_kind": document.get("dataset_kind", "saved_fixture"),
             "observed_at": entry.get("observed_at"), "evidence_ids": ids})
        for number, row in enumerate(entry.get("assets", [])):
            assets.append(_normal_asset(row, f"{ctx.step['capability']}:{index}:{number}", source,
                entry.get("observed_at"), ids, importer, importer.root))
        for number, row in enumerate(entry.get("records", [])):
            records.append({**_redact(copy.deepcopy(row)), "record_id": "replay-fixture-" + digest([key, number])[:24],
                "observed_at": row.get("observed_at") or entry.get("observed_at"),
                "execution_source": "replay", "evidence_ids": sorted(set(row.get("evidence_ids", [])) | set(ids))})
        statuses.append(state)
    status = "completed" if all(state == "completed" for state in statuses) and not importer.issues else "partial"
    if importer.issues:
        records.append({"category": "replay_summary", "issues": importer.issues, "execution_source": "replay"})
    return {"status": status, "reason": "synthetic_fixture_replayed" if document.get("dataset_kind") == "synthetic_fixture"
            else "saved_fixture_replayed", "assets": assets, "records": importer.records + records}


def replay_step(ctx):
    if ctx.run["config"].get("execution", {}).get("source") != "replay":
        return {"status": "blocked", "reason": "replay_requires_explicit_execution_source", "assets": [], "records": []}
    importer = EvidenceImporter(ctx)
    package = ctx.run["config"].get("execution", {}).get("evidence_dir")
    if package:
        path = _safe_path(importer.root, package)
        if not path.is_dir():
            return {"status": "blocked", "reason": "missing_evidence_directory", "assets": [], "records": []}
        return _package(ctx, importer, path)
    return _fixture(ctx, importer)

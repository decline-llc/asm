"""Accept a saved delivery through Workbench while denying all external I/O.

The input package is supplied explicitly; target names are read only from its
saved observations. Existing evidence, exports and quota ledgers are immutable.
This script neither reads backend secrets nor starts a service.
"""
from __future__ import annotations

import argparse
import builtins
from collections import Counter
from contextlib import ExitStack, contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dns.resolver  # noqa: E402
import dotenv  # noqa: E402
import httpx  # noqa: E402
from playwright import async_api, sync_api  # noqa: E402

from asm import conf  # noqa: E402
from asm.orchestrator import Workbench  # noqa: E402
from asm.panel.base import RateLimiter  # noqa: E402
from asm.replay import classify_historical_status  # noqa: E402
from asm.reports import ASSET_FIELDS, TABLE_FIELDS, USER_HEADERS  # noqa: E402
from asm.run_store import digest  # noqa: E402
from asm.scope import normalize_host  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hashes(directory):
    return {p.relative_to(directory).as_posix(): sha(p)
            for p in sorted(directory.rglob("*")) if p.is_file()}


def ledger_state(path):
    if not path.exists():
        return {"status": "absent"}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        rows = {}
        for (name,) in tables:
            # The ledger schema is local and trusted; quote identifiers nevertheless.
            quoted = '"' + name.replace('"', '""') + '"'
            rows[name] = sorted(connection.execute("SELECT * FROM " + quoted).fetchall(), key=repr)
    return {"status": "existing", "content_hash": digest(rows)}


@contextmanager
def deny_external():
    """Spy low-level boundaries and fail if even a blocked attempt occurs."""
    attempts = Counter()

    def denied(name):
        def fail(*args, **kwargs):
            attempts[name] += 1
            raise AssertionError("Offline acceptance attempted " + name)
        return fail

    def protected_open(original):
        def guarded(file, mode="r", *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(file))
                if any(part.lower().startswith(".env") for part in path.parts):
                    attempts["secret_file_access"] += 1
                    raise AssertionError("Offline acceptance attempted secret file access")
            return original(file, mode, *args, **kwargs)
        return guarded

    with ExitStack() as stack:
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
            stack.enter_context(patch.object(socket, name, denied("socket." + name)))
        for name in ("connect", "connect_ex", "send", "sendto", "sendall"):
            stack.enter_context(patch.object(socket.socket, name, denied("socket.socket." + name)))
        for name in ("resolve", "query"):
            stack.enter_context(patch.object(dns.resolver.Resolver, name, denied("dns." + name)))
        stack.enter_context(patch.object(httpx.HTTPTransport, "handle_request", denied("httpx.sync_transport")))
        stack.enter_context(patch.object(httpx.AsyncHTTPTransport, "handle_async_request", denied("httpx.async_transport")))
        stack.enter_context(patch.object(urllib.request, "urlopen", denied("urllib.urlopen")))
        stack.enter_context(patch.object(urllib.request.OpenerDirector, "open", denied("urllib.opener")))
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            stack.enter_context(patch.object(subprocess, name, denied("subprocess." + name)))
        for name in ("system", "popen", "startfile"):
            if hasattr(os, name):
                stack.enter_context(patch.object(os, name, denied("os." + name)))
        stack.enter_context(patch.object(sync_api, "sync_playwright", denied("playwright.sync")))
        stack.enter_context(patch.object(async_api, "async_playwright", denied("playwright.async")))
        stack.enter_context(patch.object(RateLimiter, "acquire", denied("quota.acquire")))
        stack.enter_context(patch.object(dotenv, "load_dotenv", denied("dotenv.load")))
        stack.enter_context(patch.object(conf, "load_dotenv", denied("conf.load_dotenv")))
        stack.enter_context(patch.object(builtins, "open", protected_open(builtins.open)))
        stack.enter_context(patch.object(io, "open", protected_open(io.open)))
        yield attempts
    assert not attempts, "Offline boundary was invoked: " + repr(dict(attempts))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def source_evidence_paths(package, observations, calls):
    """Count every actual saved input, including trace references outside evidence/."""
    paths = {package / "target_observations.json", package / "logs/tool-calls.jsonl"}
    paths.update(p.resolve() for p in (package / "evidence").rglob("*") if p.is_file())
    references = [value for call in calls for value in call.get("outputs", [])]
    references += [row.get("screenshot_path") or row.get("screenshot_rel") or row.get("screenshot_abs")
                   for row in observations]
    for value in references:
        if not isinstance(value, str):
            continue
        for base in (package, ROOT):
            path = (base / value).resolve()
            if path.is_relative_to(package) and path.is_file():
                paths.add(path)
                break
    return {path.relative_to(ROOT).as_posix(): sha(path) for path in paths}


def expected_investigation_hosts(observations, target):
    """Read literal saved hosts independently of the generated asset scope flags."""
    hosts = []
    target = normalize_host(target)
    for row in observations:
        link = row.get("url") or row.get("link") or ""
        value = row.get("domain") or (urlsplit(link).hostname if "://" in link else "") or row.get("host") or row.get("name", "")
        if row.get("kind") == "dns-only" and not row.get("domain") and not row.get("host") and not link:
            for ending in ("（仅 DNS）", "(DNS-only)"):
                if value.endswith(ending):
                    value = value[:-len(ending)].strip()
                    break
        try:
            host = normalize_host(value)
        except ValueError:
            continue
        if host == target or host.endswith("." + target):
            hosts.append(host)
    return hosts


def verify_snapshot(run):
    manifest = run["snapshot"]
    directory = Path(manifest["path"])
    assert manifest["status"] == "complete", "Replay delivery has missing or failed export files"
    assert manifest["run_status"] == run["status"] and run["status"] in {"completed", "partial"}
    identifiers = manifest["row_asset_ids"]
    assert identifiers["professional"] == identifiers["user_custom"]
    expected_ids = {a["asset_id"] for a in run["assets"] if a["scope_status"] == "in_scope"
                    and a["verification_status"] != "quarantined"}
    assert set(identifiers["professional"].values()) == expected_ids
    main_files = []
    for edition, stem, headers in (("professional", "专业调查报告", ASSET_FIELDS),
                                    ("user_custom", "资产梳理总结表", USER_HEADERS)):
        for suffix in ("csv", "html", "md"):
            path = directory / edition / (stem + "." + suffix)
            assert path.is_file() and path.stat().st_size
            main_files.append(path.relative_to(directory).as_posix())
        with (directory / edition / (stem + ".csv")).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        assert rows[0] == headers and len(rows) - 1 == len(expected_ids)
    tables = list((directory / "professional/tables").glob("*"))
    assert len(tables) == len(TABLE_FIELDS) * 3
    frozen = json.loads((directory / "observations.snapshot.json").read_text(encoding="utf-8"))
    assert {a["asset_id"] for a in frozen["assets"]} == {a["asset_id"] for a in run["assets"]}
    assert frozen["execution_source"] == "replay"
    assert manifest["config_hash"] == frozen["config_hash"] == digest(run["config"])
    audit = json.loads((directory / "audit.snapshot.json").read_text(encoding="utf-8"))
    for name, cutoff in audit["logs"]["files"].items():
        prefix = (Path(run["directory"]) / "logs" / name).read_bytes()[:cutoff["bytes"]]
        assert len(prefix) == cutoff["bytes"] and hashlib.sha256(prefix).hexdigest() == cutoff["sha256"]
    for entry in manifest["files"]:
        path = directory / entry["path"]
        assert path.is_file() and path.stat().st_size == entry["size"] and sha(path) == entry["sha256"]
    return {"snapshot_id": manifest["snapshot_id"], "directory": str(directory), "status": manifest["status"],
            "main_files": main_files, "main_asset_count": len(expected_ids), "table_files": len(tables),
            "file_hashes_valid": True, "same_asset_ids": True, "audit_log_prefix_hashes_valid": True}


def verify_log_views(workbench, run):
    events = workbench.store.events(run["run_id"])
    directory = Path(run["directory"])
    saved_events = read_jsonl(directory / "logs/events.jsonl")
    saved_calls = read_jsonl(directory / "logs/tool-calls.jsonl")
    assert saved_events == events
    assert saved_calls == [{"id": e["id"], **e["data"]} for e in events if e["kind"] == "tool_call"]
    assert len({e["id"] for e in events}) == len(events)
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)
    return events, saved_calls


def accept(package, run_id=None):
    package = package.resolve()
    assert package.is_relative_to(ROOT) and package.is_dir(), "Saved input must be a directory inside the workspace"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    project_id = "replay_saved_" + stamp
    output = ROOT / "data/validation/workbench-20261011" / ("replay-acceptance-" + stamp + ".json")
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "project_id": project_id,
               "input_package": str(package), "validation_kind": "disk_only_workbench_replay", "passed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with deny_external() as attempts:
        original = tree_hashes(package)
        observations = json.loads((package / "target_observations.json").read_text(encoding="utf-8-sig"))
        assert isinstance(observations, dict) and isinstance(observations.get("target"), str)
        rows = observations.get("observations", observations.get("assets", []))
        expected_scoped_hosts = expected_investigation_hosts(rows, observations["target"])
        source_calls = read_jsonl(package / "logs/tool-calls.jsonl")
        expected_evidence = source_evidence_paths(package, rows, source_calls)
        ledger = ROOT / "data/account-rate-ledger.sqlite"
        quota_before = ledger_state(ledger)
        config = {"schema_version": 2, "profile": project_id, "mode_preset": "passive_discovery", "authorization": False,
            "execution": {"source": "replay", "target_local": False, "evidence_dir": package.relative_to(ROOT).as_posix()},
            "targets": {"roots": [observations["target"]]},
            "scope_sets": {"investigation": {"include": [observations["target"]], "exclude": [], "domain_match": "subdomains"}},
            "permissions": {"search": {"allow": True, "scope_ref": "investigation"}},
            "plan": {"selection": "custom", "selected_capabilities": ["search"], "selected_tools": ["fofa"]},
            "budgets": {"max_rounds": 1, "max_hosts": max(1, len(rows)), "max_duration_seconds": 300}}
        validation = not run_id
        validation_database = ROOT / "data/validation/workbench.sqlite"
        if run_id and validation_database.exists():
            with sqlite3.connect(validation_database.as_uri() + "?mode=ro", uri=True) as connection:
                validation = connection.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone() is not None
        workbench = Workbench(ROOT, recover=False, validation=validation)
        if run_id:
            run = workbench.run(run_id)
            assert run["config"]["execution"]["source"] == "replay"
            assert (ROOT / run["config"]["execution"]["evidence_dir"]).resolve() == package
            project_id = run["project_id"]
            summary["project_id"] = project_id
            project = workbench.project(project_id)
        else:
            project = workbench.save_project(config)
            run = workbench.start(project_id, background=False)
        summary.update({"run_id": run["run_id"], "directory": run["directory"], "config_hash": digest(run["config"]),
                        "permission_version": run["config"]["permission_version"], "permission_revision": project["revision"],
                        "checkpoint": str(Path(run["directory"]) / "checkpoints/current.json")})
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        assert len(run["steps"]) == 1, "Saved package replay must not spawn new package-import feedback steps"
        assert len(run["assets"]) == len(rows), "Saved observations were lost or duplicated"
        assert all(a["execution_source"] == "replay" for a in run["assets"])
        assert all(a["verification_status"] in {"candidate_only", "dns_only", "quarantined", "replayed_verified"} for a in run["assets"])
        records = [json.loads(r["data"]) for r in workbench.store.rows("SELECT data FROM records WHERE run=?", (run["run_id"],))]
        indexed = [r for r in records if r.get("category") == "evidence_index"]
        assert len(indexed) == len(expected_evidence)
        assert len({r["evidence_id"] for r in indexed}) == len(indexed)
        assert {row["original_path"]: row["source_sha256"] for row in indexed} == expected_evidence
        for row in indexed:
            assert sha(Path(run["directory"]) / row["path"]) == row["sha256"]
        events, traces = verify_log_views(workbench, run)
        assert len(traces) == len(source_calls)
        assert sum(e["kind"] == "asset_found" for e in events) == len(rows)
        expected_health = Counter(classify_historical_status(c.get("status")) for c in source_calls)
        actual_health = Counter(c["provenance"]["status_class"] for c in traces)
        assert actual_health == expected_health
        if any(state != "completed" for state in expected_health):
            assert run["status"] == "partial", "Historical degradation must remain visible"
        assert all(c["status"] == "replayed" and c["provenance"]["new_network_requests"] == 0 for c in traces)
        first = verify_snapshot(run)
        assert first["main_asset_count"] == len(expected_scoped_hosts), "Literal in-scope saved hosts were omitted from main reports"
        frozen = tree_hashes(Path(first["directory"]))
        completed_steps = [(s["id"], s["status"], s["attempt"], s["receipt"]) for s in run["steps"]]
        asset_ids = {a["asset_id"] for a in run["assets"]}
        # Re-open the on-disk database to prove continuation does not rely on memory.
        restarted = Workbench(ROOT, recover=False, validation=validation)
        resumed = restarted.resume(run["run_id"], background=False)
        assert resumed["run_id"] == run["run_id"] and {a["asset_id"] for a in resumed["assets"]} == asset_ids
        assert [(s["id"], s["status"], s["attempt"], s["receipt"]) for s in resumed["steps"]] == completed_steps
        later_events, later_traces = verify_log_views(restarted, resumed)
        assert later_traces == traces
        assert sum(e["kind"] == "asset_found" for e in later_events) == len(rows)
        assert len(restarted.store.rows("SELECT id FROM records WHERE run=?", (run["run_id"],))) == len(records)
        assert tree_hashes(Path(first["directory"])) == frozen
        second = verify_snapshot(resumed)
        assert first["snapshot_id"] != second["snapshot_id"]
        assert tree_hashes(package) == original, "Historical package was changed"
        quota_after = ledger_state(ledger)
        assert quota_after == quota_before, "Replay changed the shared account ledger"
        summary.update({"passed": True, "run_status": resumed["status"], "delivery_status": resumed["snapshot"]["status"],
            "source_observations": len(rows), "assets": len(resumed["assets"]), "historical_traces": len(source_calls),
            "expected_in_scope_observations": len(expected_scoped_hosts),
            "evidence_index": len(indexed), "historical_status_counts": dict(expected_health),
            "verification_status_counts": dict(Counter(a["verification_status"] for a in resumed["assets"])),
            "initial_snapshot": first, "resumed_snapshot": second,
            "resume_same_run": True, "completed_steps_reexecuted": 0, "duplicate_assets": 0, "duplicate_tool_traces": 0,
            "duplicate_asset_events": 0, "old_exports_unchanged": True, "historical_package_unchanged": True,
            "event_and_log_views_match": True, "event_count_after_resume": len(later_events),
            "external_attempts": dict(attempts), "new_network_requests": 0, "secret_file_reads": 0,
            "quota_unchanged": True, "account_ledger": str(ledger), "quota_state": quota_after,
            "validation_evidence": str(output), "finished_at": datetime.now(timezone.utc).isoformat()})
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="Existing saved delivery directory inside the workspace")
    parser.add_argument("--run-id", help="Continue acceptance of an existing replay run without reimporting its evidence")
    arguments = parser.parse_args()
    return accept(arguments.package, arguments.run_id)


if __name__ == "__main__":
    raise SystemExit(main())

"""Saved packages/fixtures remain offline and retain source provenance."""
import hashlib
import json
import socket
import subprocess
import sys
from types import SimpleNamespace

import dns.resolver
import httpx
import pytest

from asm.replay import classify_historical_status, replay_step
from asm.run_store import RunStore


@pytest.fixture
def deny_external(monkeypatch):
    calls = []
    def deny(*args, **kwargs):
        calls.append("external")
        raise AssertionError("Workbench replay attempted external I/O")
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        monkeypatch.setattr(socket, name, deny)
    for name in ("connect", "connect_ex", "sendto", "sendall"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(dns.resolver.Resolver, "resolve", deny)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)
    monkeypatch.setattr(subprocess, "run", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=deny))
    yield calls
    assert calls == []


class Context:
    def __init__(self, root, *, evidence_dir=None, capability="search", target="example.invalid", source="replay"):
        self.workbench = SimpleNamespace(root=root, store=RunStore(root / "state.sqlite"))
        self.run = {"run_id": "saved_fixture_run", "directory": str(root / "new-run"),
                    "config": {"execution": {"source": source}, "permissions": {"tcp_scan": {"allow": False}}}}
        if evidence_dir is not None:
            self.run["config"]["execution"]["evidence_dir"] = evidence_dir
        self.step = {"id": "fixture-step", "capability": capability, "target": target,
                     "params": {}, "tool": "fixture"}
        self.calls = []
        self.network_permissions = []

    def require(self, *args, **kwargs):
        self.network_permissions.append(kwargs.get("network", True))
        raise AssertionError("Saved evidence import must not request new live permissions")

    def record(self, tool, params, status, outputs, provenance):
        row = {"tool": tool, "params": params, "status": status, "outputs": outputs,
               "provenance": provenance, "ts": "2026-10-11T00:00:00Z"}
        self.calls.append(row)
        self.workbench.store.event(self.run["run_id"], "tool_call", row)
        return row


def write_package(root, statuses=("completed", "\ufffdgarbled", "FOFA[820000]", "upstream 429")):
    package = root / "report/saved_delivery"
    (package / "evidence/subfolder").mkdir(parents=True)
    (package / "logs").mkdir()
    source = package / "evidence/subfolder/raw.json"
    source.write_text(json.dumps({"observed": ["192.0.2.1"], "source": "saved_fixture"}), encoding="utf-8")
    records = [{"name": "portal.example.invalid", "link": "https://portal.example.invalid:8443",
                "ip_resolution": "DNS saved:\n192.0.2.1\n192.0.2.2", "kind": "asset", "badge": "candidate"},
               {"name": "mail.example.invalid", "link": "", "ip_resolution": "192.0.2.3",
                "kind": "dns-only", "badge": "candidate"}]
    (package / "target_observations.json").write_text(json.dumps({"generated_utc": "2026-10-10T12:00:00Z",
        "observations": records}), encoding="utf-8")
    calls = [{"tool": "saved-source", "ts": "2026-10-10T11:00:00Z", "status": status,
              "outputs": ["evidence/subfolder/raw.json"], "params": {"q": "fixture-query"},
              "provenance": "historical_fixture"} for status in statuses]
    (package / "logs/tool-calls.jsonl").write_text("\n".join(json.dumps(call) for call in calls) + "\n", encoding="utf-8")
    return package, source


def test_package_preserves_bytes_timestamps_candidates_and_corrupt_status(tmp_path, deny_external):
    package, source = write_package(tmp_path)
    ctx = Context(tmp_path, evidence_dir=package.relative_to(tmp_path).as_posix())
    original_config = json.dumps(ctx.run["config"], sort_keys=True)
    result = replay_step(ctx)
    assert result["status"] == "partial"
    assert len(result["assets"]) == 2
    assert {row["verification_status"] for row in result["assets"]} == {"candidate_only", "dns_only"}
    assert all(row["observed_at"] == "2026-10-10T12:00:00Z" for row in result["assets"])
    assert result["assets"][0]["ip"] == "192.0.2.1\n192.0.2.2"
    assert result["assets"][0]["port"] == 8443
    assert len(ctx.calls) == 4 and all(call["status"] == "replayed" for call in ctx.calls)
    assert ctx.calls[1]["provenance"]["source_status"] == "\ufffdgarbled"
    assert [call["provenance"]["status_class"] for call in ctx.calls] == ["completed", "unknown", "failed", "degraded"]
    assert all(call["provenance"]["observed_at"] == "2026-10-10T11:00:00Z" for call in ctx.calls)
    assert ctx.network_permissions == [] and json.dumps(ctx.run["config"], sort_keys=True) == original_config
    evidence = [row for row in result["records"] if row["category"] == "evidence_index"]
    captured = next(row for row in evidence if row["original_path"].endswith("raw.json"))
    assert (tmp_path / "new-run" / captured["path"]).read_bytes() == source.read_bytes()
    assert captured["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert captured["source_sha256"] in captured["path"]
    assert len(ctx.workbench.store.rows("SELECT * FROM records")) == len(evidence)
    assert not (tmp_path / "data/account-rate-ledger.sqlite").exists()
    assert not deny_external


def test_partial_import_retry_deduplicates_trace_and_raw_evidence(tmp_path, deny_external):
    package, _ = write_package(tmp_path)
    ctx = Context(tmp_path, evidence_dir=str(package))
    first = replay_step(ctx)
    files = sorted((tmp_path / "new-run/evidence").iterdir())
    before = {str(path): path.stat().st_mtime_ns for path in files}
    retried = replay_step(ctx)
    assert len(ctx.calls) == 4
    assert before == {str(path): path.stat().st_mtime_ns for path in files}
    assert {row["asset_id"] for row in first["assets"]} == {row["asset_id"] for row in retried["assets"]}
    assert len(ctx.workbench.store.rows("SELECT * FROM records")) == 3


@pytest.mark.parametrize("annotation", ["（仅 DNS）", "(DNS-only)"])
def test_saved_dns_display_annotation_recovers_exact_observed_host(tmp_path, deny_external, annotation):
    package, _ = write_package(tmp_path, statuses=("completed",))
    path = package / "target_observations.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["observations"][1]["name"] = "mail.example.invalid" + annotation
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    result = replay_step(Context(tmp_path, evidence_dir=str(package)))
    asset = result["assets"][1]
    assert asset["name"] == "mail.example.invalid" + annotation
    assert asset["domain"] == "mail.example.invalid"
    assert asset["verification_status"] == "dns_only" and asset["attribution_status"] == "unconfirmed"
    assert asset["source_record"]["host_mapping"] == {
        "field": "name", "annotation": annotation, "status": "parsed_saved_literal"}


def test_dns_annotation_never_overrides_explicit_host_or_guesses_display_text(tmp_path, deny_external):
    package, _ = write_package(tmp_path, statuses=("completed",))
    path = package / "target_observations.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["observations"][1].update(name="mail.example.invalid（仅 DNS）", host="explicit.example.invalid")
    document["observations"].append({"kind": "dns-only", "name": "mail.example.invalid（仅 DNS） extra"})
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    result = replay_step(Context(tmp_path, evidence_dir=str(package)))
    assert result["assets"][1]["domain"] == "explicit.example.invalid"
    assert result["assets"][2]["domain"] == "mail.example.invalid（仅 DNS） extra"
    assert all("host_mapping" not in asset["source_record"] for asset in result["assets"])


def test_missing_package_or_fixture_never_fabricates_success(tmp_path, deny_external):
    missing = replay_step(Context(tmp_path, evidence_dir="report/no_package"))
    assert missing["status"] == "blocked" and missing["assets"] == []
    no_fixture = replay_step(Context(tmp_path))
    assert no_fixture["status"] == "blocked" and no_fixture["reason"] == "missing_replay_fixture"
    package = tmp_path / "report/empty"
    package.mkdir(parents=True)
    no_obs = replay_step(Context(tmp_path, evidence_dir=str(package)))
    assert no_obs["status"] == "blocked" and no_obs["reason"] == "missing_target_observations"


def test_generic_fixture_requires_exact_target_and_saved_capability(tmp_path, project, deny_external):
    fixtures = tmp_path / "tests/fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "workbench-replay.json").write_bytes((project / "tests/fixtures/workbench-replay.json").read_bytes())
    good = Context(tmp_path, capability="web_visit", target="http://127.0.0.1:8765")
    result = replay_step(good)
    assert result["status"] == "completed" and result["reason"] == "synthetic_fixture_replayed"
    assert result["assets"][0]["verification_status"] == "candidate_only"
    unknown = replay_step(Context(tmp_path, capability="web_visit", target="https://outside.example.invalid"))
    assert unknown["status"] == "blocked" and unknown["assets"] == []
    unavailable = replay_step(Context(tmp_path, capability="vulnerability_check"))
    assert unavailable["status"] == "blocked" and unavailable["records"] == []
    live = replay_step(Context(tmp_path, source="live"))
    assert live["status"] == "blocked" and live["reason"] == "replay_requires_explicit_execution_source"


@pytest.mark.parametrize("value", ["../outside", ".env", "report/.env.private", "../../tmp/evidence"])
def test_replay_path_boundary_never_reads_secret_or_outside_files(tmp_path, value, deny_external):
    with pytest.raises(ValueError, match="project|secret"):
        replay_step(Context(tmp_path, evidence_dir=value))


def test_redacts_saved_credentials_but_keeps_source_hash(tmp_path, deny_external):
    package, source = write_package(tmp_path, statuses=("completed",))
    source.write_text(json.dumps({"token": "DUMMY_SECRET_ONLY", "endpoint": "https://fixture.invalid?key=DUMMY_URL_KEY"}), encoding="utf-8")
    ctx = Context(tmp_path, evidence_dir=str(package))
    result = replay_step(ctx)
    row = next(row for row in result["records"] if row.get("original_path", "").endswith("raw.json"))
    output = (tmp_path / "new-run" / row["path"]).read_text(encoding="utf-8")
    assert "DUMMY_SECRET_ONLY" not in output and "DUMMY_URL_KEY" not in output
    assert "REDACTED" in output and row["redacted"]
    assert row["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert row["sha256"] != row["source_sha256"]


@pytest.mark.parametrize("raw,state", [("\ufffdgarbled", "unknown"), ("FOFA[820000]", "failed"),
    ("upstream 429", "degraded"), ("completed", "completed"), ("stopped", "interrupted"),
    ("200 but unavailable detail", "unknown")])
def test_historical_status_does_not_repair_unknown_text(raw, state):
    assert classify_historical_status(raw) == state

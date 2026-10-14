"""Real loopback DNS workers, durable subactions and cooperative cancellation."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time

import dns.message
import dns.rdatatype
import pytest

from asm import active_tools
from asm.orchestrator import Workbench
from tests.fixtures import dns_server


class Metrics:
    def __init__(self, delay):
        self.delay, self.active, self.maximum = delay, 0, 0
        self.lock, self.requests = threading.Lock(), []
        self.on_first = None

    def install(self, monkeypatch):
        original = dns_server.UDP.handle

        def handle(handler):
            query = dns.message.from_wire(handler.request[0])
            with self.lock:
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                self.requests.append({"domain": str(query.question[0].name).rstrip("."),
                                      "rtype": dns.rdatatype.to_text(query.question[0].rdtype), "at": time.monotonic()})
                first = len(self.requests) == 1
            try:
                if first and self.on_first:
                    self.on_first()
                time.sleep(self.delay)
                original(handler)
            finally:
                with self.lock:
                    self.active -= 1

        monkeypatch.setattr(dns_server.UDP, "handle", handle)


@pytest.fixture
def root(tmp_path, project, monkeypatch):
    (tmp_path / "profiles").mkdir()
    shutil.copy2(project / "profiles/modes.yaml", tmp_path / "profiles/modes.yaml")
    monkeypatch.setattr("asm.conf.load_dotenv", lambda *_args, **_kwargs: pytest.fail("DNS fixture never reads .env"))
    return tmp_path


def config(fixture, capability="dns_recursive", workers=2, maximum_calls=30):
    now = datetime.now(timezone.utc)
    # Synthetic .invalid questions go only to the owned 127.0.0.1 DNS fixture.
    # Current target_local host policy does not accept synthetic DNS names.
    return {
        "schema_version": 2, "profile": "dns_workers", "mode_preset": "full_asm", "authorization": True,
        "authorization_details": {"authority": "fixture_owner", "reference": "self_owned_loopback_dns_fixture",
                                  "environment": "local_lab", "window": {"start": (now - timedelta(hours=1)).isoformat(),
                                                                         "end": (now + timedelta(hours=1)).isoformat()}},
        "execution": {"source": "live", "target_local": False},
        "targets": {"roots": ["fixture.invalid"], "ip_cidrs": []},
        "scope_sets": {name: {"include": ["fixture.invalid"], "exclude": [], "domain_match": "subdomains"}
                       for name in ("investigation", "verification", "extended")},
        "permissions": {capability: {"allow": True, "scope_ref": "extended" if capability == "dns_enum" else "verification"}},
        "plan": {"selection": "custom", "selected_capabilities": [capability],
                 "params": {capability: {"resolvers": [f"127.0.0.1:{fixture.port}"], "workers": workers,
                                         "record_types": ["A", "AAAA"], "timeout_seconds": 2, "requests_per_second": 1000,
                                         "dictionary": ["api", "mail"], "wildcard_baseline_queries": 2}}},
        "budgets": {"max_rounds": 1, "max_duration_seconds": 60, "per_tool": {capability: {"max_calls": maximum_calls}}},
    }


def start(wb, settings):
    project = wb.save_project(settings)
    return wb.start(project["project_id"], background=False)


@pytest.mark.parametrize("capability", ["dns_recursive", "dns_enum"])
def test_configured_workers_make_real_concurrent_local_queries(root, monkeypatch, capability):
    # 0.5s per query: loaded CI runners can otherwise schedule the second worker after the first
    # query finished, which would make the overlap assertion below depend on machine speed.
    metrics = Metrics(0.5)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({"fixture.invalid": {"A": ["127.0.0.1"], "AAAA": ["::1"]},
                                     "api.fixture.invalid": {"A": ["127.0.0.1"]}, "mail.fixture.invalid": {"A": ["127.0.0.2"]}})
    try:
        wb = Workbench(root)
        serial = start(wb, config(fixture, capability, workers=1))
        assert serial["status"] == "completed"
        assert metrics.maximum == 1
        serial_count = len(metrics.requests)
        serial_starts = [item["at"] for item in metrics.requests]
        assert min(b - a for a, b in zip(serial_starts, serial_starts[1:])) >= 0.45
        metrics.maximum = 0
        parallel = start(wb, config(fixture, capability, workers=2))
        assert parallel["status"] == "completed"
        assert metrics.maximum == 2
        assert len(metrics.requests) == serial_count * 2
        concurrent_starts = [item["at"] for item in metrics.requests[serial_count:]]
        assert concurrent_starts[1] - concurrent_starts[0] < metrics.delay
        rows = wb.store.rows("SELECT data FROM records WHERE run=? AND category='dns_observations' ORDER BY rowid", (parallel["run_id"],))
        observations = [json.loads(row["data"]) for row in rows]
        evidence_ids = [row["evidence_ids"][0] for row in observations]
        assert len(evidence_ids) == len(set(evidence_ids)) == serial_count
        receipts = wb.store.rows("SELECT * FROM action_receipts WHERE run=?", (parallel["run_id"],))
        assert {row["evidence_id"] for row in receipts} == set(evidence_ids)
        for row in receipts:
            assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]
    finally:
        fixture.close()


def test_missing_permission_sends_no_dns_packet(root, monkeypatch):
    metrics = Metrics(0)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({})
    try:
        settings = config(fixture, workers=8)
        settings["permissions"]["dns_recursive"]["allow"] = False
        run = start(Workbench(root), settings)
        assert run["steps"][0]["status"] == "skipped"
        assert "function_permission_denied" in run["steps"][0]["reason"]
        assert not metrics.requests
    finally:
        fixture.close()


def test_parallel_queries_respect_one_durable_call_budget(root, monkeypatch):
    metrics = Metrics(0.2)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({"fixture.invalid": {"A": ["127.0.0.1"]}})
    try:
        wb = Workbench(root)
        settings = config(fixture, workers=8, maximum_calls=1)
        settings["plan"]["params"]["dns_recursive"]["record_types"] = ["A", "AAAA", "MX", "NS", "CNAME"]
        run = start(wb, settings)
        assert run["status"] == "partial"
        assert run["steps"][0]["status"] == "quota-exhausted"
        assert len(metrics.requests) == 1
        assert len([event for event in wb.store.events(run["run_id"]) if event["kind"] == "tool_started"]) == 1
        resumed = wb.resume(run["run_id"], background=False)
        assert resumed["run_id"] == run["run_id"]
        assert len(metrics.requests) == 1
        assert len([event for event in wb.store.events(run["run_id"]) if event["kind"] == "tool_started"]) == 1
    finally:
        fixture.close()


def test_resume_keeps_baseline_names_receipts_and_total_budget(root, monkeypatch):
    metrics = Metrics(0.02)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({"api.fixture.invalid": {"A": ["127.0.0.1"]}, "mail.fixture.invalid": {"A": ["127.0.0.2"]}})
    original = active_tools._query_observation
    interrupted = False

    def interrupt_after_saved_first_query(*args, **kwargs):
        nonlocal interrupted
        result = original(*args, **kwargs)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt("Fixture interruption after durable DNS receipt")
        return result

    monkeypatch.setattr(active_tools, "_query_observation", interrupt_after_saved_first_query)
    try:
        wb = Workbench(root)
        settings = config(fixture, "dns_enum", workers=1, maximum_calls=4)
        with pytest.raises(KeyboardInterrupt):
            start(wb, settings)
        run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
        stopped = wb.run(run_id)
        assert stopped["status"] == "interrupted" and len(metrics.requests) == 1
        first = wb.store.rows("SELECT * FROM action_receipts WHERE run=?", (run_id,))[0]
        old_bytes = Path(first["path"]).read_bytes()
        reopened = Workbench(root)
        resumed = reopened.resume(run_id, background=False)
        # The original root is complete. Automatic feedback queues child roots,
        # which truthfully exhaust this four-call budget without extra packets.
        assert resumed["status"] == "partial" and resumed["run_id"] == run_id
        assert resumed["steps"][0]["status"] == "completed"
        assert len(metrics.requests) == 4
        baseline_names = [item["domain"] for item in metrics.requests if item["domain"].startswith("asm-")]
        assert len(baseline_names) == len(set(baseline_names)) == 2
        assert Path(first["path"]).read_bytes() == old_bytes
        assert len(reopened.store.rows("SELECT * FROM action_receipts WHERE run=?", (run_id,))) == 4
        assert len([event for event in reopened.store.events(run_id) if event["kind"] == "tool_started"]) == 4
        assert len(resumed["assets"]) == 2
    finally:
        fixture.close()


def test_cancellation_stops_inflight_dns_polling_and_dispatch(root, monkeypatch):
    metrics = Metrics(0.8)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({})
    original_exchange, durations = active_tools._dns_exchange, []

    def exchange(*args, **kwargs):
        beginning = time.monotonic()
        try:
            return original_exchange(*args, **kwargs)
        finally:
            durations.append(time.monotonic() - beginning)

    monkeypatch.setattr(active_tools, "_dns_exchange", exchange)
    try:
        wb = Workbench(root)
        metrics.on_first = lambda: wb.control(wb.store.rows("SELECT id FROM runs")[0]["id"], "pause")
        settings = config(fixture, workers=2)
        settings["plan"]["params"]["dns_recursive"]["record_types"] = ["A", "AAAA", "MX", "NS", "CNAME"]
        settings["plan"]["params"]["dns_recursive"]["timeout_seconds"] = 10
        run = start(wb, settings)
        assert run["status"] == "paused"
        assert durations and max(durations) < 1.5
        assert 1 <= len(metrics.requests) <= 2
        count = len(metrics.requests)
        time.sleep(0.9)
        assert len(metrics.requests) == count
        assert run["snapshot"]["run_status"] == "paused"
    finally:
        fixture.close()


def test_recursive_depth_and_duplicate_queries_are_bounded(root, monkeypatch):
    metrics = Metrics(0)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({"fixture.invalid": {"CNAME": ["first.fixture.invalid"]},
                                     "first.fixture.invalid": {"CNAME": ["second.fixture.invalid"]},
                                     "second.fixture.invalid": {"A": ["127.0.0.1"]}})
    try:
        wb = Workbench(root)
        settings = config(fixture, maximum_calls=2)
        params = settings["plan"]["params"]["dns_recursive"]
        params.update({"record_types": ["CNAME", "CNAME"], "resolvers": [f"127.0.0.1:{fixture.port}"] * 2, "max_cname_hops": 1})
        run = start(wb, settings)
        assert run["status"] == "completed"
        assert [item["domain"] for item in metrics.requests] == ["fixture.invalid", "first.fixture.invalid"]
        gaps = [json.loads(row["data"]) for row in wb.store.rows("SELECT data FROM records WHERE run=? AND category='dns_coverage_gaps'", (run["run_id"],))]
        assert gaps[0]["domain"] == "second.fixture.invalid" and gaps[0]["reason"] == "max_cname_hops_exhausted"
    finally:
        fixture.close()


def test_dictionary_budget_snapshot_and_resume_ignore_source_changes(root, monkeypatch):
    metrics = Metrics(0)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({"api.fixture.invalid": {"A": ["127.0.0.1"]}, "mail.fixture.invalid": {"A": ["127.0.0.2"]}})
    dictionary = root / "dictionary.txt"
    dictionary.write_text("api\nmail\nunselected\n", encoding="utf-8")
    original = active_tools._query_observation
    interrupted = False

    def interruption(*args, **kwargs):
        nonlocal interrupted
        record = original(*args, **kwargs)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        return record

    monkeypatch.setattr(active_tools, "_query_observation", interruption)
    try:
        wb = Workbench(root)
        settings = config(fixture, "dns_enum", workers=1, maximum_calls=4)
        settings["plan"]["params"]["dns_enum"].update({"dictionary": "dictionary.txt", "max_candidates_per_root": 2})
        with pytest.raises(KeyboardInterrupt):
            start(wb, settings)
        run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
        manifest = next((Path(wb.run(run_id)["directory"]) / "checkpoints").glob("dns-dictionary-*.json"))
        old_manifest = manifest.read_bytes()
        dictionary.write_text("changed\n", encoding="utf-8")
        resumed = Workbench(root).resume(run_id, background=False)
        assert resumed["status"] == "partial" and resumed["steps"][0]["status"] == "completed"
        assert {item["domain"] for item in metrics.requests if not item["domain"].startswith("asm-")} == {"api.fixture.invalid", "mail.fixture.invalid"}
        assert manifest.read_bytes() == old_manifest
    finally:
        fixture.close()


@pytest.mark.parametrize("capability,param,value", [("dns_recursive", "workers", 33), ("dns_recursive", "workers", 1.5),
                                                    ("dns_recursive", "timeout_seconds", 61), ("dns_recursive", "max_cname_hops", 65),
                                                    ("dns_enum", "wildcard_baseline_queries", 9), ("dns_enum", "max_candidates_per_root", 100001),
                                                    ("dns_enum", "dictionary", ".env")])
def test_invalid_execution_bounds_send_no_packet(root, monkeypatch, capability, param, value):
    metrics = Metrics(0)
    metrics.install(monkeypatch)
    fixture = dns_server.DNSFixture({})
    try:
        settings = config(fixture, capability)
        settings["plan"]["params"][capability][param] = value
        try:
            run = start(Workbench(root), settings)
        except ValueError as error:
            # Shared configuration validation can reject recursive DNS bounds
            # before a run exists; the execution adapter also validates its input.
            assert capability == "dns_recursive"
            assert {"workers": "dns.workers", "timeout_seconds": "dns.timeout", "max_cname_hops": "dns.max_cname_hops"}[param] in str(error)
        else:
            assert run["status"] == "partial" and run["steps"][0]["status"] == "failed"
        assert not metrics.requests
    finally:
        fixture.close()

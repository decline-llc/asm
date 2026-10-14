import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from asm.cli import main
from asm.orchestrator import Workbench, parse_target
from asm.workbench_tools import result, web_visit
from tests.fixtures.server import start_server


@pytest.fixture
def workbench_root(tmp_path, project, monkeypatch):
    (tmp_path / "profiles").mkdir()
    shutil.copy(project / "profiles/modes.yaml", tmp_path / "profiles/modes.yaml")
    monkeypatch.setattr("asm.conf.load_dotenv", lambda *_args, **_kwargs: pytest.fail("Read .env"))
    return tmp_path


def configuration(urls):
    return {"schema_version": 2, "profile": "unit", "mode_preset": "authorized_verify", "authorization": True,
        "execution": {"source": "live", "target_local": True},
        "targets": {"roots": ["localhost"], "ip_cidrs": ["127.0.0.1/32"]},
        "scope_sets": {key: {"include": ["localhost", "127.0.0.1/32"], "exclude": []} for key in ("investigation", "verification", "extended")},
        "permissions": {"web_visit": {"allow": True, "scope_ref": "verification"}},
        "plan": {"selection": "custom", "selected_capabilities": ["web_visit"], "selected_tools": ["target_http"],
            "params": {"web_visit": {"urls": urls, "timeout_seconds": 2}}},
        "web": {"urls": urls}, "budgets": {"max_rounds": 1, "max_duration_seconds": 60}}


def local_asset(ctx):
    value = ctx.call("target_http", {"url": ctx.target}, lambda: {"observed": True})
    assert value["observed"]
    return result(ctx, [{"name": "localhost", "domain": "localhost", "port": 8765, "protocol": "tcp",
        "url": ctx.target, "sources": ["fixture"], "verification_status": "verified", "evidence_ids": [ctx.last_evidence_id]}])


def test_input_types():
    assert parse_target("192.0.2.1")["kind"] == "ip"
    assert parse_target("example.invalid")["kind"] == "domain"
    assert parse_target("Fixture Organization")["kind"] == "subject"
    with pytest.raises(ValueError):
        parse_target("a\nb")


def test_backend_reopen_keeps_already_delivered_stopped_run_unchanged(workbench_root):
    def stop(ctx):
        ctx.workbench.control(ctx.run["run_id"], "stop")
        ctx.check_control()
    wb = Workbench(workbench_root, adapters={"web_visit": stop})
    item = wb.save_project(configuration(["http://localhost:8765"]))
    run = wb.start(item["project_id"], background=False)
    assert run["status"] == "stopped" and run["snapshot"]["run_status"] == "stopped"
    events = wb.store.events(run["run_id"])
    frozen = {p: p.read_bytes() for p in (Path(run["directory"]) / "exports").rglob("*") if p.is_file()}
    reopened = Workbench(workbench_root)
    assert reopened.run(run["run_id"])["snapshot"] == run["snapshot"]
    assert reopened.store.events(run["run_id"]) == events
    assert all(path.read_bytes() == raw for path, raw in frozen.items())


def test_success_events_dual_snapshot_and_resume_no_reexecution(workbench_root):
    calls = []
    def adapter(ctx):
        calls.append(ctx.target)
        return local_asset(ctx)
    wb = Workbench(workbench_root, adapters={"web_visit": adapter})
    project = wb.save_project(configuration(["http://localhost:8765/a", "http://localhost:8765/b"]))
    run = wb.start(project["project_id"], background=False)
    assert run["status"] == "completed" and len(run["assets"]) == 1
    assert len(calls) == 2
    assert run["snapshot"]["status"] == "complete"
    path = Path(run["directory"])
    old_exports = {str(p): p.read_bytes() for p in (path / "exports").rglob("*") if p.is_file()}
    trace = [json.loads(line) for line in (path / "logs/tool-calls.jsonl").read_text(encoding="utf-8").splitlines()]
    events = [e for e in wb.store.events(run["run_id"]) if e["kind"] == "tool_call"]
    assert trace == [{"id": e["id"], **e["data"]} for e in events]
    resumed = wb.resume(run["run_id"], background=False)
    assert resumed["run_id"] == run["run_id"] and len(calls) == 2
    assert all(Path(p).read_bytes() == raw for p, raw in old_exports.items())
    assert len(list((path / "exports").iterdir())) == 2
    with pytest.raises(ValueError):
        wb.artifact(run["run_id"], "../../../../.env")


def test_interrupt_restart_revocation_and_partial_delivery(workbench_root):
    calls = []
    def interrupted(ctx):
        calls.append(ctx.target)
        if ctx.target.endswith("/b"):
            raise KeyboardInterrupt
        return local_asset(ctx)
    wb = Workbench(workbench_root, adapters={"web_visit": interrupted})
    config = configuration(["http://localhost:8765/a", "http://localhost:8765/b"])
    project = wb.save_project(config)
    with pytest.raises(KeyboardInterrupt):
        wb.start(project["project_id"], background=False)
    run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
    run = wb.run(run_id)
    assert run["status"] == "interrupted"
    assert [s["status"] for s in run["steps"]] == ["completed", "interrupted"]
    assert run["snapshot"]["run_status"] == "interrupted"
    original_config = run["config"]
    config["permissions"]["web_visit"]["allow"] = False
    wb.save_project(config, project_id=project["project_id"])
    reopened = Workbench(workbench_root, adapters={"web_visit": local_asset})
    resumed = reopened.resume(run_id, background=False)
    assert calls == ["http://localhost:8765/a", "http://localhost:8765/b"]
    assert resumed["config"] == original_config
    assert resumed["steps"][1]["status"] == "skipped"
    assert "function_permission_denied" in resumed["steps"][1]["reason"]
    assert len(resumed["assets"]) == 1


def test_pause_stops_dispatch_and_resume_preserves_receipts(workbench_root):
    calls = []
    def pausing(ctx):
        calls.append(ctx.target)
        output = local_asset(ctx)
        ctx.workbench.control(ctx.run["run_id"], "pause")
        return output
    wb = Workbench(workbench_root, adapters={"web_visit": pausing})
    project = wb.save_project(configuration(["http://localhost:8765/a", "http://localhost:8765/b"]))
    run = wb.start(project["project_id"], background=False)
    assert run["status"] == "paused" and len(calls) == 1
    wb.adapters = {"web_visit": local_asset}
    resumed = wb.resume(run["run_id"], background=False)
    assert resumed["status"] == "completed"
    assert all(s["attempt"] == 1 for s in resumed["steps"])


def test_real_web_only_does_not_request_paths_screenshots_or_outside(workbench_root):
    server = start_server()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        wb = Workbench(workbench_root, adapters={"web_visit": web_visit})
        project = wb.save_project(configuration([url]))
        run = wb.start(project["project_id"], background=False)
        assert run["status"] == "completed"
        assert server.requests == ["/"]
        assert run["assets"][0]["title"] == "Fixture Asset Portal"
        assert not list(Path(run["directory"]).rglob("*.png"))
    finally:
        server.shutdown()
        server.server_close()


def test_outside_web_has_zero_transport_calls(workbench_root):
    wb = Workbench(workbench_root, adapters={"web_visit": lambda _ctx: pytest.fail("External call")})
    config = configuration(["http://192.0.2.1"])
    # A configured out-of-scope object is rejected before the adapter is entered.
    project = wb.save_project(config)
    run = wb.start(project["project_id"], background=False)
    assert run["steps"][0]["status"] == "skipped"


def test_add_investigation_scope_preserves_active_permissions(workbench_root):
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    project = wb.save_project(configuration(["http://localhost:8765"]))
    before = project["config"]["scope_sets"]["verification"]
    updated = wb.add_scope(project["project_id"], "example.invalid")
    assert "example.invalid" in updated["config"]["scope_sets"]["investigation"]["include"]
    assert updated["config"]["scope_sets"]["verification"] == before
    with pytest.raises(ValueError):
        wb.add_scope(project["project_id"], "example.invalid", scope_ref="verification")


def test_quota_is_read_only_and_unknown_not_zero(workbench_root, monkeypatch):
    path = workbench_root / "missing" / "quota.sqlite"
    runner = CliRunner()
    with monkeypatch.context() as context:
        context.chdir(workbench_root)
        wb = Workbench(workbench_root)
        config = wb.save_project(configuration([]))["path"]
        response = runner.invoke(main, ["quota", "--profile", str(config), "--db", str(path)])
        assert response.exit_code == 0
        assert json.loads(response.output)["status"] == "no_ledger"
        assert not path.parent.exists()
        path.parent.mkdir()
        path.write_bytes(b"invalid ledger")
        response = runner.invoke(main, ["quota", "--profile", str(config), "--db", str(path)])
        assert response.exit_code == 0
        assert json.loads(response.output)["status"] == "unknown"
        assert json.loads(response.output)["used"] is None
        with sqlite3.connect(path.with_name("valid.sqlite")) as conn:
            conn.execute("CREATE TABLE sources(source TEXT,day TEXT,used INT,quota INT)")
            conn.execute("INSERT INTO sources VALUES('fofa','2026-10-11',11,12)")
        response = runner.invoke(main, ["quota", "--profile", str(config), "--db", str(path.with_name("valid.sqlite"))])
        assert response.exit_code == 0
        assert json.loads(response.output)["rows"][0]["used"] == 11


def test_action_receipt_survives_interrupted_step_without_repeating_call(workbench_root):
    calls = []
    def adapter(ctx):
        output = ctx.call("target_http", {"url": ctx.target}, lambda: calls.append(ctx.target) or {"ok": True})
        if len(calls) == 1 and ctx.step["attempt"] == 0:
            raise KeyboardInterrupt
        assert output["ok"]
        return result(ctx)
    wb = Workbench(workbench_root, adapters={"web_visit": adapter})
    wb.save_project(configuration(["http://localhost:8765"]))
    with pytest.raises(KeyboardInterrupt):
        wb.start("unit", background=False)
    run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
    resumed = wb.resume(run_id, background=False)
    assert resumed["status"] == "completed" and len(calls) == 1
    assert len([e for e in wb.store.events(run_id) if e["kind"] == "tool_call"]) == 1


def test_receipt_write_before_merge_is_recovered(workbench_root, monkeypatch):
    calls = []
    def adapter(ctx):
        calls.append(ctx.target)
        return local_asset(ctx)
    wb = Workbench(workbench_root, adapters={"web_visit": adapter})
    wb.save_project(configuration(["http://localhost:8765"]))
    original_merge = wb._merge
    monkeypatch.setattr(wb, "_merge", lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        wb.start("unit", background=False)
    run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
    receipt = wb.run(run_id)["steps"][0]["receipt"]
    assert Path(receipt).is_file()
    monkeypatch.setattr(wb, "_merge", original_merge)
    assert wb.resume(run_id, background=False)["status"] == "completed"
    assert len(calls) == 1


def test_budget_shared_across_targets_and_pending_restart_recoverable(workbench_root, monkeypatch):
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    config = configuration(["http://localhost:8765/a", "http://localhost:8765/b"])
    config["budgets"]["per_tool"] = {"web_visit": {"max_calls": 1}}
    wb.save_project(config)
    monkeypatch.setattr(wb, "_launch", lambda *_args, **kwargs: kwargs["lease"].close())
    run = wb.start("unit", background=False)
    assert run["status"] == "pending"
    reopened = Workbench(workbench_root, adapters={"web_visit": local_asset})
    assert reopened.run(run["run_id"])["status"] == "interrupted"
    resumed = reopened.resume(run["run_id"], background=False)
    assert resumed["status"] == "partial"
    assert len([e for e in reopened.store.events(run["run_id"]) if e["kind"] == "tool_call"]) == 1
    assert resumed["steps"][1]["status"] == "quota-exhausted"


def test_feedback_outbox_survives_post_merge_crash(workbench_root, monkeypatch):
    def parent(ctx):
        if ctx.target == "localhost":
            return result(ctx, [{"name": "child.localhost", "domain": "child.localhost", "sources": ["fixture"]}])
        return result(ctx)
    wb = Workbench(workbench_root, adapters={"search": parent})
    config = configuration([])
    config["mode_preset"] = "passive_discovery"
    config["execution"]["target_local"] = False
    config["plan"] = {"selection": "custom", "selected_capabilities": ["search"], "selected_tools": ["fofa"]}
    config["permissions"] = {"search": {"allow": True, "scope_ref": "investigation"}}
    config["scope_sets"]["investigation"]["domain_match"] = "subdomains"
    config["budgets"]["max_rounds"] = 2
    wb.save_project(config)
    original = wb._drain_feedback
    calls = 0
    def fail_after_merge(run_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(run_id)
    monkeypatch.setattr(wb, "_drain_feedback", fail_after_merge)
    with pytest.raises(KeyboardInterrupt):
        wb.start("unit", background=False)
    run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
    monkeypatch.setattr(wb, "_drain_feedback", original)
    resumed = wb.resume(run_id, background=False)
    assert resumed["status"] == "completed"
    assert {s["target"] for s in resumed["steps"]} == {"localhost", "127.0.0.1", "child.localhost"}

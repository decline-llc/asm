import copy

import pytest

from asm.orchestrator import Workbench
from asm.run_store import digest
from tests.unit.test_orchestrator import configuration, local_asset, workbench_root  # noqa: F401


def test_preview_matches_initial_multisource_queue_and_never_executes(workbench_root, monkeypatch):  # noqa: F811
    config = configuration(["http://localhost:8765/first", "http://127.0.0.1:8765/second"])
    config["budgets"]["max_hosts"] = 1
    wb = Workbench(workbench_root, adapters={"web_visit": local_asset})
    item = wb.save_project(config)
    for target in ("subprocess.Popen", "socket.create_connection", "asm.conf.load_dotenv"):
        monkeypatch.setattr(target, lambda *_a, **_k: pytest.fail("Preview must not execute"))
    before = wb.project(item["project_id"])
    preview = wb.plan(item["project_id"])
    assert len(preview["steps"]) == 1
    assert preview["steps"][0]["can_execute"]
    assert preview["config_hash"] == digest(before["config"])
    assert not wb.store.rows("SELECT * FROM runs")
    assert wb.project(item["project_id"]) == before
    run = wb.start(item["project_id"], background=False)
    assert [(s["capability"], s["tool"], s["target"], s["params"]) for s in run["steps"]] == [
        (s["capability"], s["tool"], s["target"], s["params"]) for s in preview["steps"]]


def test_preview_distinguishes_missing_dependency_permission_and_typed_subject(workbench_root, monkeypatch):  # noqa: F811
    config = configuration(["http://localhost:8765"])
    config["mode_preset"] = "full_asm"
    config["targets"]["company"] = "Fixture Organization"
    config["scope_sets"]["investigation"]["subjects"] = ["Fixture Organization"]
    config["permissions"].update({"tcp_scan": {"allow": True, "scope_ref": "verification"},
                                  "company_lookup": {"allow": True, "scope_ref": "investigation"}})
    config["permissions"]["web_visit"]["allow"] = False
    config["plan"]["selected_capabilities"] = ["company_lookup", "tcp_scan", "web_visit"]
    config["plan"]["selected_tools"] = ["company_evidence_import", "nmap", "target_http"]
    monkeypatch.setattr("asm.preflight._wsl_distribution", lambda _: {"status": "blocked", "reason": "fixture_missing_distribution"})
    wb = Workbench(workbench_root)
    item = wb.save_project(config)
    preview = wb.plan(item["project_id"])
    company, tcp, web = preview["steps"]
    assert company["target"] == "Fixture Organization" and company["permitted"]
    assert tcp["permitted"] and not tcp["can_execute"]
    assert tcp["dependencies"]["reason"] == "fixture_missing_distribution"
    assert not web["permitted"] and web["reason"] == "function_permission_denied"


def test_capability_specific_urls_and_revocation_change_preview(workbench_root):  # noqa: F811
    config = configuration(["http://localhost:8765/"])
    config["permissions"]["screenshot"] = {"allow": True, "scope_ref": "verification"}
    config["plan"]["selected_capabilities"].append("screenshot")
    config["plan"]["selected_tools"].append("playwright")
    config["plan"]["params"]["screenshot"] = {"urls": ["http://localhost:8765/login"]}
    wb = Workbench(workbench_root)
    item = wb.save_project(config)
    first = wb.plan(item["project_id"])
    assert [s["target"] for s in first["steps"]] == ["http://localhost:8765/", "http://localhost:8765/login"]
    changed = copy.deepcopy(config)
    changed["permissions"]["screenshot"]["allow"] = False
    wb.save_project(changed, project_id=item["project_id"])
    second = wb.plan(item["project_id"])
    assert first["config_hash"] != second["config_hash"]
    assert first["permission_version"] != second["permission_version"]
    assert not second["steps"][1]["can_execute"]

import json

import httpx
import pytest

from asm.orchestrator import Workbench
from tests.unit.test_orchestrator import workbench_root  # noqa: F401


def config():
    return {"schema_version": 2, "profile": "indexes", "mode_preset": "passive_discovery", "authorization": False,
        "execution": {"source": "live", "target_local": False}, "targets": {"roots": ["fixture.invalid"]},
        "scope_sets": {"investigation": {"include": ["fixture.invalid"], "domain_match": "exact"}},
        "permissions": {"passive_subdomains": {"allow": True, "scope_ref": "investigation"}},
        "plan": {"selection": "custom", "selected_capabilities": ["passive_subdomains"],
            "selected_tools": ["certificate_indexes", "archive_indexes"], "params": {"passive_subdomains": {
                "sources": ["certificate_indexes", "archive_indexes"], "timeout_seconds": 1}}},
        "budgets": {"max_rounds": 1, "max_hosts": 10, "max_duration_seconds": 60}}


@pytest.mark.parametrize("ct_failure", [False, True])
def test_index_union_source_failure_dedup_outside_not_requested(workbench_root, monkeypatch, ct_failure):  # noqa: F811
    calls = []
    original_client = httpx.Client

    def reply(request):
        calls.append((request.url.host, str(request.url)))
        if request.url.host == "crt.sh":
            return httpx.Response(503) if ct_failure else httpx.Response(200, json=[{"name_value": "fixture.invalid\nexternal.invalid"}])
        assert request.url.host == "web.archive.org"
        return httpx.Response(200, json=[["original"], ["https://fixture.invalid/login"], ["https://other.invalid/"]])

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(reply)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    monkeypatch.setattr("socket.getaddrinfo", lambda *_a, **_k: pytest.fail("Unexpected DNS"))
    wb = Workbench(workbench_root)
    item = wb.save_project(config())
    run = wb.start(item["project_id"], background=False)
    assert len(calls) == 2 and [host for host, _ in calls] == ["crt.sh", "web.archive.org"]
    assert run["status"] == ("partial" if ct_failure else "completed")
    inside = [a for a in run["assets"] if a["scope_status"] == "in_scope"]
    assert len(inside) == 1
    assert set(inside[0]["sources"]) == ({"web.archive.org"} if ct_failure else {"crt.sh", "web.archive.org"})
    assert any(a["domain"] == "other.invalid" and a["scope_status"] == "out_of_scope" for a in run["assets"])
    wb.resume(run["run_id"], background=False)
    assert len(calls) == 2


def test_passive_collector_saved_flags_are_validated(workbench_root):  # noqa: F811
    from asm.utils.oneforall import PASSIVE_FLAGS
    report = workbench_root / "saved-report.json"
    observations = workbench_root / "saved-rows.json"
    report.write_text(json.dumps({"root": "fixture.invalid", "mode": "passive", "status": "completed", "flags": dict.fromkeys(PASSIVE_FLAGS, False)}))
    observations.write_text(json.dumps([{"subdomain": "fixture.invalid"}]))
    value = config()
    value["plan"]["selected_tools"] = ["oneforall_passive"]
    value["plan"]["params"]["passive_subdomains"] = {"sources": ["oneforall_passive"],
        "oneforall_report": report.name, "oneforall_observations": observations.name}
    wb = Workbench(workbench_root)
    item = wb.save_project(value)
    assert wb.start(item["project_id"], background=False)["assets"][0]["verification_status"] == "candidate_only"
    report.write_text(json.dumps({"root": "fixture.invalid", "mode": "passive", "flags": dict.fromkeys(PASSIVE_FLAGS, True)}))
    run = wb.start(item["project_id"], background=False)
    assert run["status"] == "partial" and not run["assets"]

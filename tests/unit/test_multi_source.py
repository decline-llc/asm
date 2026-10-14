import pytest

from asm.orchestrator import Workbench
from asm.policy import ExecutionPolicy
from tests.unit.test_policy import project, resolve
from tests.unit.test_orchestrator import workbench_root  # noqa: F401


def test_multiple_selected_sources_are_real_independent_steps(workbench_root):  # noqa: F811
    value = project(mode_preset="passive_discovery", authorization=False,
        targets={"roots": ["example.invalid"]},
        permissions={"search": {"allow": True, "scope_ref": "investigation"}},
        plan={"selection": "custom", "selected_capabilities": ["search"],
            "selected_tools": ["fofa", "quake"], "params": {"search": {"engines": ["fofa", "quake"]}}})
    value["scope_sets"]["investigation"]["subjects"] = []
    calls = []

    def adapter(ctx):
        calls.append(ctx.step["tool"])
        ctx.call(ctx.step["tool"], {"target": ctx.target}, lambda: {"source": ctx.step["tool"]})
        if ctx.step["tool"] == "fofa":
            return {"status": "partial", "reason": "fixture_source_failed", "assets": [], "records": []}
        return {"status": "completed", "assets": [{"asset_id": "shared", "domain": "example.invalid", "sources": ["quake"]}], "records": []}

    wb = Workbench(workbench_root, adapters={"search": adapter})
    item = wb.save_project(value)
    run = wb.start(item["project_id"], background=False)
    assert calls == ["fofa", "quake"]
    assert run["status"] == "partial" and len(run["assets"]) == 1
    assert len(run["steps"]) == 2
    assert {s["tool"] for s in run["steps"]} == {"fofa", "quake"}
    wb.resume(run["run_id"], background=False)
    assert calls == ["fofa", "quake"]


def test_source_subset_and_explicit_native_tool_override_defaults():
    data = resolve(project(permissions={"search": {"allow": True, "scope_ref": "investigation"}}, plan={"selection": "custom", "selected_capabilities": ["search"],
        "selected_tools": ["quake"], "params": {"search": {"engines": ["fofa", "quake"]}}}))
    policy = ExecutionPolicy(data)
    assert policy.tools_for("search") == ["quake"]
    assert policy.check("search", "example.invalid", tool="fofa", network=False).reason == "tool_not_selected"
    native = resolve(project(tools={"tcp_scan": "python_socket"},
        plan={"selection": "custom", "selected_capabilities": ["tcp_scan"]}))
    assert native["tools"]["tcp_scan"] == "python_socket"
    assert native["plan"]["params"]["tcp_scan"]["engine"] == "python_socket"


def test_conflicting_or_unknown_tool_configuration_rejected():
    with pytest.raises(ValueError, match="conflicts"):
        resolve(project(tools={"tcp_scan": "python_socket"}, plan={"selection": "custom",
            "selected_capabilities": ["tcp_scan"], "params": {"tcp_scan": {"engine": "nmap"}}}))
    with pytest.raises(ValueError, match="Unknown source"):
        resolve(project(plan={"selection": "custom", "selected_capabilities": ["search"],
            "params": {"search": {"engines": ["typo"]}}}))

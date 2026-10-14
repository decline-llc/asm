from pathlib import Path

import pytest

from asm import active_tools
from asm.orchestrator import Workbench, RunControlled
from tests.unit.test_orchestrator import configuration, workbench_root  # noqa: F401
from tests.unit.test_active_tools import Context


def test_split_batches_resume_completed_scans_without_repeating_calls(workbench_root, monkeypatch):  # noqa: F811
    value = configuration([])
    value["mode_preset"] = "full_asm"
    value["permissions"] = {"tcp_scan": {"allow": True, "scope_ref": "verification"}}
    value["plan"] = {"selection": "custom", "selected_capabilities": ["tcp_scan"], "selected_tools": ["nmap"],
                     "params": {"tcp_scan": {"ports": "80-84", "split_batches": True, "batch_size": 2}}}
    calls, pause_once = [], [True]

    def scan(ctx, args):
        ports = args[args.index("-p") + 1]
        calls.append(ports)
        if ports == "82,83" and pause_once[0]:
            pause_once[0] = False
            ctx.workbench.control(ctx.run["run_id"], "pause")
            raise RunControlled("pausing")
        return {"exit_code": 0, "stdout": '<nmaprun><host><address addr="127.0.0.1" addrtype="ipv4"/><ports>' +
                ''.join(f'<port protocol="tcp" portid="{port}"><state state="open"/></port>' for port in ports.split(",")) +
                '</ports></host></nmaprun>'}

    monkeypatch.setattr(active_tools, "_run_scanner", scan)
    wb = Workbench(workbench_root)
    item = wb.save_project(value)
    run = wb.start(item["project_id"], background=False)
    assert run["status"] == "paused" and calls == ["80,81", "82,83"]
    evidence_before = {path: path.read_bytes() for path in (Path(run["directory"]) / "evidence").rglob("*") if path.is_file()}
    final = wb.resume(run["run_id"], background=False)
    assert final["status"] == "completed" and calls == ["80,81", "82,83", "82,83", "84"]
    assert {asset["port"] for asset in final["assets"]} == set(range(80, 85))
    assert all(path.read_bytes() == raw for path, raw in evidence_before.items())
    assert len(list((Path(run["directory"]) / "evidence").rglob("nmap-*.xml"))) == 3


def test_scanner_failure_stops_further_batches_and_preserves_covered_ports(tmp_path, monkeypatch):
    ctx = Context(tmp_path, "tcp_scan", "nmap", params={"ports": "1-5", "split_batches": True, "batch_size": 2})
    calls = []
    def scan(_ctx, args):
        calls.append(args[args.index("-p") + 1])
        return {"exit_code": 0 if len(calls) == 1 else 2, "stdout": "<nmaprun/>"}
    monkeypatch.setattr(active_tools, "_run_scanner", scan)
    result = active_tools.port_service(ctx)
    assert result["status"] == "partial" and calls == ["1,2", "3,4"]
    assert result["records"][0]["covered_ports"] == [1, 2]


def test_scripts_do_not_silently_run_under_service_permission_and_slow_rate_is_honored(tmp_path, monkeypatch):
    ctx = Context(tmp_path, "service_probe", "nmap", params={"ports": "80", "approved_script_categories": ["default"]})
    with pytest.raises(active_tools.PolicyDenied, match="require_deep_service"):
        active_tools.port_service(ctx)
    assert not ctx.calls
    ctx = Context(tmp_path, "tcp_scan", "python_socket", params={"ports": "8765", "packets_per_second": 0.25})
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def settimeout(self, _): pass
        def connect(self, _): raise ConnectionRefusedError
    monkeypatch.setattr(active_tools.socket, "socket", lambda *_: Connection())
    active_tools.port_service(ctx)
    assert ctx.waits == [4]

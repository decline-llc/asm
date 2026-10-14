"""Adapter contracts and real local broker transport; no external traffic."""
import base64
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading

import httpx
import pytest

from asm import active_tools, external_tools
from asm.orchestrator import Workbench
from asm.policy import ExecutionPolicy
from tests.unit.test_active_tools import Context
from tests.unit.test_orchestrator import configuration, workbench_root  # noqa: F401
from tests.unit.test_policy import resolve


def test_selected_web_tools_have_independent_queue_and_per_tool_params():
    value = configuration(["http://localhost:8765/"])
    value["plan"]["selected_tools"] = ["target_http", "httpx"]
    value["plan"]["params"]["web_visit"]["tool_options"] = {"httpx": {"timeout_seconds": 9}}
    config = resolve(value)
    policy = ExecutionPolicy(config)
    assert policy.tools_for("web_visit") == ["target_http", "httpx"]
    assert policy.params("web_visit", "httpx")["timeout_seconds"] == 9
    assert policy.params("web_visit", "target_http")["timeout_seconds"] == 2
    bad = configuration(["http://localhost:8765/"])
    bad["plan"]["params"]["web_visit"]["tool_options"] = {"httpx": {"requests_per_second": -2}}
    with pytest.raises(ValueError, match="positive"):
        resolve(bad)


def test_naabu_validates_output_and_batch_coverage(tmp_path, monkeypatch):
    ctx = Context(tmp_path, "tcp_scan", "naabu", params={"ports": "80,443", "split_batches": True, "batch_size": 1})
    monkeypatch.setattr(active_tools, "_run_scanner", lambda _ctx, args, **kw: {"exit_code": 0, "stdout": json.dumps({"ip": "127.0.0.1", "port": int(args[3]), "protocol": "tcp"})})
    result = external_tools.port_scan(ctx)
    assert [a["port"] for a in result["assets"]] == [80, 443]
    assert [r["covered_ports"] for r in result["records"]] == [[80], [443]]
    monkeypatch.setattr(active_tools, "_run_scanner", lambda *_a, **_kw: {"exit_code": 0, "stdout": '{"ip":"192.0.2.2","port":80}'})
    with pytest.raises(ValueError, match="Unexpected"):
        external_tools.port_scan(ctx)


@pytest.mark.parametrize("tool,output", [
    ("dig_probe", ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\nexample.invalid. 60 IN A 198.18.0.1\n"),
    ("dnsx", '{"host":"example.invalid","status_code":"NOERROR","a":["198.18.0.1"]}\n'),
])
def test_external_dns_preserves_rejected_fake_ip(tmp_path, monkeypatch, tool, output):
    ctx = Context(tmp_path, "dns_recursive", tool, target="example.invalid")
    monkeypatch.setattr(active_tools, "_run_scanner", lambda *_a, **_k: {"exit_code": 0, "stdout": output})
    raw = external_tools.dns_query(ctx, "example.invalid", "A", "127.0.0.1:5300")
    assert raw["status"] == "NOERROR"
    assert not raw["answers"][0]["accepted"]
    assert raw["answers"][0]["value"] == "198.18.0.1"


def test_broker_only_relays_get_head_and_preserves_binary_response(tmp_path):
    source = Path(__file__).resolve().parents[2] / "tools/http_tool_runner.py"
    spec = importlib.util.spec_from_file_location("asm_test_broker", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SPEC = {"timeout": 2}
    seen = []
    def reply(frame):
        seen.append(frame)
        module.PENDING[frame["id"]].put({"status": 200, "headers": {"content-type": "image/png"}, "body_base64": base64.b64encode(b"\x89PNG\x00\xff").decode()})
    module.emit = reply
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Proxy)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(proxy="http://127.0.0.1:" + str(server.server_port), trust_env=False) as client:
            result = client.get("http://authorized.invalid/image.png")
            assert result.content == b"\x89PNG\x00\xff"
            assert seen[0]["url"] == "http://authorized.invalid/image.png"
            assert client.post("http://authorized.invalid/post", content=b"payload").status_code == 501
            assert len(seen) == 1
            assert client.get("http://authorized.invalid/", headers={"Upgrade": "websocket"}).status_code == 405
            assert len(seen) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_namespace_command_and_scope_isolation_contract():
    source = Path(__file__).resolve().parents[2] / "tools/http_tool_runner.py"
    spec = importlib.util.spec_from_file_location("asm_broker_command", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = {"target": "https://authorized.invalid/", "rate": 2, "timeout": 5, "depth": 2,
            "crawl_scope": "^https://authorized.invalid/", "templates": ["approved.yaml"]}
    for tool in external_tools.HTTP_TOOLS:
        args = module.command({**base, "tool": tool}, "http://127.0.0.1:1")
        assert "http://127.0.0.1:1" in args
        if tool == "katana":
            assert "-dr" in args and "-cs" in args
        if tool == "nuclei":
            assert "-ni" in args and "-pt" in args and "-dr" in args


def test_approved_templates_exclude_implicit_other_protocols_and_raw_requests(tmp_path):
    ctx = Context(tmp_path, "vulnerability_check", "nuclei")
    path = tmp_path / "check.yaml"
    ctx.params = {"approved_templates": ["check.yaml"]}
    path.write_text("id: fixture\ninfo: {name: fixture}\nhttp:\n  - method: GET\n    path: ['{{BaseURL}}/fixture']\n", encoding="utf-8")
    assert external_tools.approved_templates(ctx)
    path.write_text("id: fixture\nhttp:\n  - raw: ['GET / HTTP/1.1']\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        external_tools.approved_templates(ctx)
    path.write_text("id: fixture\nhttp: [{method: GET}]\ndns: [{name: external.invalid}]", encoding="utf-8")
    with pytest.raises(ValueError, match="Only explicit HTTP"):
        external_tools.approved_templates(ctx)


def test_http_receipt_missing_observation_cannot_report_success(tmp_path):
    ctx = Context(tmp_path, "web_visit", "httpx")
    ctx.records = []
    ctx.run["directory"] = str(tmp_path)
    result = external_tools.parse_http_result(ctx, {"exit_code": 0, "protocol_completed": True, "artifacts": {}, "requests": []})
    assert result["status"] == "failed"


def test_broker_result_enters_dual_reports_and_resume_reuses_actions(workbench_root, monkeypatch):  # noqa: F811
    value = configuration(["http://localhost:8765/"])
    value["plan"]["selected_tools"] = ["httpx"]
    monkeypatch.setattr("asm.preflight._wsl_distribution", lambda *_a: {"status": "unverified", "reason": "fixture"})
    calls = []
    def run(ctx, spec, files):
        calls.append(spec["tool"])
        result_file = ctx.output_directory / "httpx.jsonl"
        result_file.write_text(json.dumps({"url": ctx.target, "status_code": 200, "title": "External fixture", "tech": ["Fixture"]}) + "\n", encoding="utf-8")
        ctx._evidence("fixture-raw", result_file, "external_tool_output")
        return {"exit_code": 0, "protocol_completed": True, "artifacts": {"tool.stdout": result_file.relative_to(ctx.run["directory"]).as_posix()},
                "requests": [{"url": ctx.target, "status": 200, "evidence_id": "fixture-raw"}], "transport": "fixture_broker"}
    monkeypatch.setattr(external_tools, "_http_job", run)
    wb = Workbench(workbench_root)
    item = wb.save_project(value)
    run = wb.start(item["project_id"], background=False)
    assert run["status"] == "completed" and calls == ["httpx"]
    assert run["assets"][0]["title"] == "External fixture"
    assert "httpx" in run["assets"][0]["sources"]
    assert run["snapshot"]["status"] == "complete"
    wb.resume(run["run_id"], background=False)
    assert calls == ["httpx"]


def test_missing_wsl_is_blocked_before_external_tool_launch(workbench_root, monkeypatch):  # noqa: F811
    value = configuration(["http://localhost:8765/"])
    value["plan"]["selected_tools"] = ["httpx"]
    monkeypatch.setattr("asm.preflight._wsl_distribution", lambda *_a: {"status": "blocked", "reason": "fixture_missing_wsl"})
    monkeypatch.setattr(external_tools, "_http_job", lambda *_a: pytest.fail("Launched unavailable tool"))
    wb = Workbench(workbench_root)
    item = wb.save_project(value)
    run = wb.start(item["project_id"], background=False)
    assert run["steps"][0]["status"] == "blocked"
    assert run["steps"][0]["reason"] == "fixture_missing_wsl"


def test_default_runtime_reuses_original_ubuntu(monkeypatch):
    from asm.bridge import Bridge
    monkeypatch.delenv("WSL_DISTRO", raising=False)
    assert Bridge().distro == "Ubuntu"
    monkeypatch.setenv("WSL_DISTRO", "ChosenExistingDistro")
    assert Bridge().distro == "ChosenExistingDistro"


def test_gowitness_exit_zero_without_image_is_partial(tmp_path):
    ctx = Context(tmp_path, "screenshot", "gowitness", target="http://127.0.0.1:8765/")
    ctx.run["directory"] = str(tmp_path)
    ctx.last_evidence_id = "tool_receipt"
    (tmp_path / "result.jsonl").write_text(json.dumps({"url": ctx.target, "failed": True,
        "failed_reason": "context deadline exceeded"}) + "\n", encoding="utf-8")
    raw = {"exit_code": 0, "protocol_completed": True, "artifacts": {"result.jsonl": "result.jsonl"},
           "requests": [{"url": ctx.target, "status": 200, "evidence_id": "http_receipt"}]}
    result = external_tools.parse_http_result(ctx, raw)
    assert result["status"] == "partial" and result["assets"] == []
    assert any(r.get("screenshot_complete") is False for r in result["records"])


def test_runtime_setup_never_creates_distribution_from_empty_inventory(monkeypatch):
    import subprocess
    import sys
    source = Path(__file__).resolve().parents[2] / "scripts/prepare_tool_runtime.py"
    spec = importlib.util.spec_from_file_location("asm_test_prepare_runtime", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    def restricted_inventory(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
    monkeypatch.setattr(module.subprocess, "run", restricted_inventory)
    monkeypatch.setattr(sys, "argv", [str(source), "--distro", "Ubuntu"])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert calls == [["wsl.exe", "--list", "--quiet"]]

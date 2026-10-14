"""Real loopback fixture checks and scanner command isolation; no internet."""
import shutil
import socketserver
import ssl
import subprocess
import threading
from types import SimpleNamespace

import pytest

from asm import active_tools
from asm.policy import PolicyDenied
from tests.fixtures.dns_server import DNSFixture
from tests.fixtures.server import tcp_listener, udp_listener


class Context:
    def __init__(self, tmp_path, capability, tool, target="127.0.0.1", params=None):
        self.workbench = SimpleNamespace(root=tmp_path)
        self.capability, self.target = capability, target
        self.params = params or {"ports": "8765"}
        self.step = {"tool": tool, "id": "fixture_step"}
        self.run = {"config": {"execution": {"source": "live", "target_local": True}, "dns": {"reject_fake_ip": True}}, "assets": []}
        self.output_directory = tmp_path / "output"
        self.last_evidence_id = None
        self.calls, self.requests, self.waits = [], [], []
        self.revoked, self.deny_suffix = False, "external.invalid"

    def require(self, target, network=True):
        self.requests.append((target, network))
        if self.revoked or str(target).endswith(self.deny_suffix):
            raise PolicyDenied("fixture_revoked_or_outside_scope")

    def call(self, tool, params, fn):
        self.calls.append((tool, params))
        data = fn()
        self.last_evidence_id = "evidence_" + str(len(self.calls))
        return data

    def wait(self, seconds):
        self.waits.append(seconds)
        self.check_control()

    def check_control(self):
        if self.revoked:
            raise PolicyDenied("fixture_revoked")


def test_tcp_socket_real_fixture_observes_port_without_service_probe(tmp_path):
    listener = tcp_listener(0)
    try:
        port = listener.getsockname()[1]
        ctx = Context(tmp_path, "tcp_scan", "python_socket", params={"ports": str(port), "timeout_seconds": 1, "packets_per_second": 5})
        result = active_tools.port_service(ctx)
        assert result["status"] == "completed"
        assert result["assets"][0]["port"] == port
        assert result["assets"][0]["verification_status"] == "observed"
        assert "service" not in result["assets"][0]
        assert ctx.calls[0][0] == "python_socket" and ctx.waits == [0.2]
        assert all(host == "127.0.0.1" for host, _ in ctx.requests)
    finally:
        listener.close()


def test_udp_socket_real_fixture_observes_reply_and_unknown_no_reply(tmp_path):
    listener = udp_listener(0)
    try:
        port = listener.getsockname()[1]
        ctx = Context(tmp_path, "udp_scan", "python_socket", params={"ports": str(port), "probe_payload": "fixture", "timeout_seconds": 1})
        result = active_tools.port_service(ctx)
        assert result["assets"][0]["proto"] == "udp"
        assert bytes.fromhex(result["records"][0]["response_hex"]) == b"FIXTURE:fixture"
    finally:
        listener.close()


@pytest.mark.parametrize("capability,expected", [("tcp_scan", "-sT"), ("udp_scan", "-sU"), ("service_probe", "-sV")])
def test_nmap_capabilities_do_not_bind_other_actions(tmp_path, capability, expected):
    ctx = Context(tmp_path, capability, "nmap", params={"ports": "80,443"})
    args = active_tools.scanner_args(ctx)
    assert expected in args and "-n" in args and "-Pn" in args and "-sC" not in args
    if capability != "service_probe":
        assert "-sV" not in args and "--script" not in args
    assert ("-sU" in args) == (capability == "udp_scan")


def test_deep_service_only_runs_explicit_approved_probe(tmp_path):
    ctx = Context(tmp_path, "deep_service_probe", "nmap", params={"ports": "443", "approved_probes": []})
    assert active_tools.scanner_args(ctx) is None
    ctx.params["approved_probes"] = ["ssl-cert"]
    args = active_tools.scanner_args(ctx)
    assert args[args.index("--script") + 1] == "ssl-cert" and "-sV" not in args and "-sC" not in args
    ctx.params["approved_probes"] = ["/tmp/unapproved.nse"]
    assert active_tools.scanner_args(ctx) is None


def test_service_uses_only_previously_observed_target_ports(tmp_path):
    ctx = Context(tmp_path, "service_probe", "nmap", params={"version_detection": True})
    ctx.run["assets"] = [{"host": "127.0.0.1", "port": 8766, "proto": "tcp"},
                         {"host": "127.0.0.2", "port": 9876}, {"host": "127.0.0.1", "port": 8767, "proto": "udp"}]
    args = active_tools.scanner_args(ctx)
    assert args[args.index("-p") + 1] == "8766"


def test_masscan_does_not_invoke_service_probe(tmp_path):
    ctx = Context(tmp_path, "tcp_scan", "masscan", params={"ports": "80,443", "packets_per_second": 25})
    args = active_tools.scanner_args(ctx)
    assert "--rate" in args and "-sV" not in args and "nmap" not in args


def test_selected_unavailable_scanner_does_not_fall_back(tmp_path, monkeypatch):
    ctx = Context(tmp_path, "tcp_scan", "nmap")
    monkeypatch.setattr(active_tools, "_run_scanner", lambda *_args: {"availability": "unavailable", "exit_code": None})
    monkeypatch.setattr(active_tools, "_native_probe", lambda *_args: pytest.fail("No implicit fallback"))
    assert active_tools.port_service(ctx)["status"] == "blocked"
    assert ctx.calls[0][0] == "nmap"


def test_scanner_revocation_terminates_process_group(tmp_path, monkeypatch):
    ctx = Context(tmp_path, "tcp_scan", "nmap")
    controls = []
    ctx.bridge = SimpleNamespace(command=lambda *_args, **_kwargs: "nmap -n -Pn", argv=lambda *_args, **_kwargs: ["fixture"],
                                 control=lambda script, **kwargs: controls.append((script, kwargs)))
    process = SimpleNamespace(returncode=None, poll=lambda: None, terminate=lambda: controls.append(("terminated", {})), wait=lambda **_kwargs: None)
    monkeypatch.setattr(active_tools.subprocess, "Popen", lambda *_args, **_kwargs: process)
    previous = ctx.require
    count = 0

    def revoke(target, network=True):
        nonlocal count
        count += 1
        if count > 1:
            ctx.revoked = True
        return previous(target, network)

    ctx.require = revoke
    with pytest.raises(PolicyDenied):
        active_tools._run_scanner(ctx, ["-n", "-Pn"])
    assert any("kill -TERM" in script for script, _ in controls)
    assert any(script == "terminated" for script, _ in controls)


def test_port_target_does_not_resolve_domain_or_accept_fake_ip(tmp_path):
    for target in ("fixture.invalid", "198.18.0.1"):
        ctx = Context(tmp_path, "tcp_scan", "nmap", target=target)
        with pytest.raises(ValueError):
            active_tools.scanner_args(ctx)
        assert not ctx.calls


def test_nmap_parser_result_keeps_raw_xml_and_evidence(tmp_path, monkeypatch):
    ctx = Context(tmp_path, "tcp_scan", "nmap")
    xml = '<nmaprun><host><address addr="127.0.0.1"/><ports><port protocol="tcp" portid="8765"><state state="open"/></port></ports></host></nmaprun>'
    monkeypatch.setattr(active_tools, "_run_scanner", lambda *_args: {"exit_code": 0, "stdout": xml})
    result = active_tools.port_service(ctx)
    assert next(ctx.output_directory.glob("nmap-*.xml")).read_text(encoding="utf-8") == xml
    assert result["assets"][0]["port"] == 8765 and result["assets"][0]["evidence_ids"] == ["evidence_1"]


def test_dns_real_local_fixture_all_record_types_and_fake_ip(tmp_path):
    fixture = DNSFixture({"fixture.invalid": {"A": ["127.0.0.1", "198.18.0.2"], "AAAA": ["::1"],
                                             "MX": ["10 mail.fixture.invalid"], "NS": ["ns.fixture.invalid"]}})
    try:
        ctx = Context(tmp_path, "dns_recursive", "dnspython", "fixture.invalid",
                      {"resolvers": [f"127.0.0.1:{fixture.port}"], "record_types": ["A", "AAAA", "MX", "NS"],
                       "timeout_seconds": 1, "reject_fake_ip": True})
        result = active_tools.dns_recursive(ctx)
        assert result["status"] == "completed"
        assert {row["query_type"] for row in result["records"]} == {"A", "AAAA", "MX", "NS"}
        assert {asset["ip"] for asset in result["assets"]} == {"127.0.0.1", "::1"}
        rejected = [answer for row in result["records"] for answer in row["answers"] if not answer["accepted"]]
        assert rejected[0]["value"] == "198.18.0.2"
        assert all(params["resolver"].startswith("127.0.0.1:") for _, params in ctx.calls)
    finally:
        fixture.close()


def test_dns_multiple_upstream_difference_is_inference(tmp_path):
    fixtures = [DNSFixture({"fixture.invalid": {"A": [ip]}}) for ip in ("127.0.0.1", "127.0.0.2")]
    try:
        ctx = Context(tmp_path, "dns_recursive", "dnspython", "fixture.invalid",
                      {"resolvers": [f"127.0.0.1:{fixture.port}" for fixture in fixtures], "record_types": ["A"], "timeout_seconds": 1})
        result = active_tools.dns_recursive(ctx)
        comparison = [row for row in result["records"] if row["category"] == "dns_comparison"][0]
        assert comparison["knowledge"] == "inference" and comparison["classification"] == "multi_upstream_difference"
    finally:
        for fixture in fixtures:
            fixture.close()


def test_dns_cname_out_of_scope_is_recorded_without_followup(tmp_path):
    fixture = DNSFixture({"fixture.invalid": {"CNAME": ["external.invalid"]}})
    try:
        ctx = Context(tmp_path, "dns_recursive", "dnspython", "fixture.invalid",
                      {"resolvers": [f"127.0.0.1:{fixture.port}"], "record_types": ["CNAME"], "timeout_seconds": 1})
        result = active_tools.dns_recursive(ctx)
        assert len(ctx.calls) == 1
        assert result["records"][-1]["reason"] == "cname_outside_function_scope"
    finally:
        fixture.close()


def test_dns_local_mode_blocks_external_resolver_before_query(tmp_path):
    ctx = Context(tmp_path, "dns_recursive", "dnspython", "fixture.invalid", {"resolvers": ["1.1.1.1"], "record_types": ["A"]})
    with pytest.raises(PolicyDenied):
        active_tools.dns_recursive(ctx)
    assert not ctx.calls


def test_dns_enum_dictionary_budget_and_wildcard_baselines(tmp_path):
    fixture = DNSFixture({"api.fixture.invalid": {"A": ["127.0.0.1"]}})
    try:
        ctx = Context(tmp_path, "dns_enum", "dnspython_dictionary", "fixture.invalid",
                      {"resolvers": [f"127.0.0.1:{fixture.port}"], "dictionary": ["api", "unselected"],
                       "max_candidates_per_root": 1, "wildcard_baseline_queries": 2, "timeout_seconds": 1})
        result = active_tools.dns_enum(ctx)
        assert len(ctx.calls) == 3
        assert result["assets"][0]["host"] == "api.fixture.invalid"
        assert not result["assets"][0]["wildcard_match"]
        assert all("unselected" not in params["domain"] for _, params in ctx.calls)
    finally:
        fixture.close()


def test_dns_dictionary_cannot_read_outside_project(tmp_path):
    ctx = Context(tmp_path, "dns_enum", "dnspython_dictionary", "fixture.invalid", {"dictionary": "../outside_dictionary.txt"})
    with pytest.raises(ValueError):
        active_tools.dns_enum(ctx)
    assert not ctx.calls


def test_tls_does_not_resolve_hostname_or_visit_http(tmp_path):
    for target in ("http://127.0.0.1:80", "https://fixture.invalid:443"):
        ctx = Context(tmp_path, "tls_inspect", "native_tls", target, {"collect_protocols": False})
        assert active_tools.tls_inspect(ctx)["status"] == "skipped"
        assert not ctx.calls


def test_tls_real_local_fixture_collects_certificate_and_protocol(tmp_path):
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("Local OpenSSL is required to generate the synthetic fixture certificate")
    cert, key = tmp_path / "fixture_cert.pem", tmp_path / "fixture_key.pem"
    generated = subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                                "-keyout", key.as_posix(), "-out", cert.as_posix(), "-subj", "/CN=localhost",
                                "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"], capture_output=True, timeout=30)
    assert generated.returncode == 0, "Synthetic fixture certificate generation failed"

    class TLSHandler(socketserver.BaseRequestHandler):
        def handle(self):
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), TLSHandler)
    server.daemon_threads = True
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(cert, key)
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        ctx = Context(tmp_path, "tls_inspect", "native_tls", f"https://127.0.0.1:{server.server_address[1]}",
                      {"collect_protocols": True, "collect_certificate_chain": True, "timeout_seconds": 2})
        result = active_tools.tls_inspect(ctx)
        assert result["status"] == "completed" and result["assets"][0]["tls_protocol"].startswith("TLSv")
        cert_record = result["records"][0]
        assert len(cert_record["certificate_sha256"]) == 64
        assert cert_record["trust_validation"] == "not_performed"
        assert "BEGIN CERTIFICATE" in cert_record["certificate_pem"]
        assert "PRIVATE KEY" not in str(result)
        assert len(ctx.calls) == 3 and len(list(ctx.output_directory.glob("leaf-*.pem"))) == 3
    finally:
        server.shutdown()
        server.server_close()


def test_registry_covers_seven_active_capabilities():
    assert set(active_tools.adapters()) == {"tcp_scan", "udp_scan", "service_probe", "deep_service_probe",
                                            "dns_recursive", "dns_enum", "tls_inspect"}

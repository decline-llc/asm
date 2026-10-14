"""Native M5 adapters through the real Workbench and a loopback-only HTTP server."""
import json
import shutil
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import httpx

from asm.orchestrator import Workbench
from asm.policy import PolicyDenied
from asm.workbench_tools import ExecutionContext, canonical_web_url, result, tool_registry


TOOLS = {"web_crawl": "native_crawler", "js_analysis": "native_js_analyzer",
    "vulnerability_check": "native_risk_checks", "takeover_probe": "stage_5_takeover_fingerprint",
    "auth_audit": "native_auth_audit", "dns_recursive": "dnspython",
    "web_visit": "target_http", "screenshot": "playwright"}


@pytest.fixture
def m5_fixture(tmp_path, project, monkeypatch):
    (tmp_path / "profiles").mkdir()
    shutil.copy(project / "profiles/modes.yaml", tmp_path / "profiles/modes.yaml")
    monkeypatch.setattr("asm.conf.load_dotenv", lambda *_a, **_kw: pytest.fail("Unexpected secret read"))
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_a, **_kw: pytest.fail("Unexpected secret read"))
    original_resolver = socket.getaddrinfo
    def local_only(host, *args, **kwargs):
        assert host in {"127.0.0.1", "localhost", "::1"}, "Unexpected non-local resolution"
        return original_resolver(host, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", local_only)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.requests.append({"path": self.path, "origin": self.headers.get("Origin", "")})
            if self.path == "/disconnect":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if self.path == "/private-redirect":
                self.send_response(302)
                self.send_header("Location", "/login")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            routes = {
                "/": (200, '<a href="/child#one">child</a><a href="/child#two">same child</a>'
                    '<a href="http://192.0.2.29/foreign">foreign</a>'
                    '<script src="/a.js#one"></script><script src="/a.js#two"></script>'
                    '<script src="/b.js"></script><script src="http://192.0.2.29/foreign.js"></script>'),
                "/child": (200, '<a href="/#again">home</a><a href="/grand">grand</a>'),
                "/grand": (200, "Fixture grandchild"),
                "/a.js": (200, 'const a="/api/local";const b="http://192.0.2.29/api/foreign";' + "X" * 300),
                "/b.js": (200, 'const c="/api/second";'),
                "/takeover": (404, "There isn't a GitHub Pages site here"),
                "/private": (401, "Fixture denial"), "/open": (200, "Fixture anonymous content"),
                "/login": (200, "Fixture login page"),
                "/login-form": (200, '<title>Owned fixture login</title><form><input type="password" name="password"></form>'),
            }
            status, body = routes.get(self.path, (404, "Fixture not found"))
            raw = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            if self.headers.get("Origin"):
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Access-Control-Allow-Credentials", "true")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield tmp_path, server, "http://localhost:" + str(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def run_capability(fixture, capability, params=None, path="/", extras=(), adapters=None, source="live", budget=None):
    root, server, base = fixture
    capabilities = [*extras, capability]
    config = {"schema_version": 2, "profile": "m5_fixture", "mode_preset": "full_asm", "authorization": True,
        "execution": {"source": source, "target_local": True}, "targets": {"roots": ["localhost"]},
        "scope_sets": {key: {"include": ["localhost", "127.0.0.1/32"], "exclude": []}
            for key in ("investigation", "verification", "extended")},
        "permissions": {cap: {"allow": True, "scope_ref": "extended"} for cap in capabilities},
        "plan": {"selection": "custom", "selected_capabilities": capabilities,
            "selected_tools": [TOOLS[cap] for cap in capabilities],
            "params": {capability: {"timeout_seconds": 2, "requests_per_second": 1000, **(params or {})}}},
        "web": {"urls": [base + path]}, "budgets": {"max_rounds": 1, "max_hosts": 5, "max_duration_seconds": 60, **(budget or {})}}
    wb = Workbench(root, adapters={**tool_registry(), **adapters} if adapters else None)
    project = wb.save_project(config)
    run = wb.start(project["project_id"], background=False)
    records = [json.loads(row["data"]) for row in wb.store.rows("SELECT data FROM records WHERE run=?", (run["run_id"],))]
    return wb, run, records


def test_explicit_login_url_captures_real_png_and_both_reports_keep_evidence(m5_fixture):
    _, server, base = m5_fixture
    wb, run, _ = run_capability(m5_fixture, "screenshot", {"urls": [base + "/login-form"]}, extras=("web_visit",))
    assert run["status"] == "completed"
    assert [step["target"] for step in run["steps"]] == [base + "/", base + "/login-form"]
    assert len(run["assets"]) == 1
    asset = run["assets"][0]
    assert asset["screenshot_kind"] == "login" and asset["login_screenshot_path"] == asset["screenshot_path"]
    directory = Path(run["directory"])
    image = directory / asset["login_screenshot_path"]
    assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    exported = directory / "exports" / run["snapshot"]["snapshot_id"]
    user_csv = next((exported / "user_custom").glob("*.csv")).read_text(encoding="utf-8-sig")
    assert "登录页面截图" in user_csv and "未取得登录页" not in user_csv
    professional = next((exported / "professional").glob("*.html")).read_text(encoding="utf-8")
    assert "登录页面截图" in professional and "data:image/png;base64," in professional
    requests = list(server.requests)
    wb.resume(run["run_id"], background=False)
    assert server.requests == requests


def test_canonical_urls_never_carry_credentials_or_fragments():
    assert canonical_web_url("http://LOCALHOST:80/path?q=1#fragment") == "http://localhost/path?q=1"
    assert canonical_web_url("/child#one", "http://localhost:8765/") == "http://localhost:8765/child"
    for url in ("http://user:secret@localhost/", "javascript:alert(1)", "http://localhost:bad/",
            "http://localhost/?api_key=fixture"):
        with pytest.raises(ValueError):
            canonical_web_url(url)


def test_real_crawler_deduplicates_cycles_and_holds_foreign_links(m5_fixture):
    _, server, base = m5_fixture
    _, run, records = run_capability(m5_fixture, "web_crawl", {"max_depth": 2, "max_urls_per_host": 10})
    assert run["status"] == "completed"
    assert [row["path"] for row in server.requests] == ["/", "/child", "/grand"]
    assert len([row for row in records if row["category"] == "web_endpoints"]) == 3
    foreign = [row for row in records if row["category"] == "out_of_scope_leads"]
    assert len(foreign) == 1 and foreign[0]["url"] == "http://192.0.2.29/foreign"
    assert foreign[0]["evidence_ids"]
    assert all(asset["url"].startswith(base) for asset in run["assets"])


@pytest.mark.parametrize("params,expected,reason", [
    ({"max_depth": 1, "max_urls_per_host": 10}, ["/", "/child"], "max_depth_exhausted"),
    ({"max_depth": 2, "max_urls_per_host": 1}, ["/"], "max_urls_per_host_exhausted"),
    ({"max_depth": 2, "max_urls_per_host": 10, "max_urls_total": 1}, ["/"], "max_urls_total_exhausted"),
])
def test_crawler_limits_affect_actual_requests(m5_fixture, params, expected, reason):
    _, server, _ = m5_fixture
    _, _, records = run_capability(m5_fixture, "web_crawl", params)
    assert [row["path"] for row in server.requests] == expected
    assert any(row.get("reason") == reason for row in records)


def test_js_actual_file_and_byte_limits_hold_endpoints_without_requests(m5_fixture):
    _, server, base = m5_fixture
    _, run, records = run_capability(m5_fixture, "js_analysis", {"max_files_per_host": 1, "max_bytes_per_file": 96})
    assert run["status"] == "completed"
    assert [row["path"] for row in server.requests] == ["/", "/a.js"]
    candidate = next(row for row in records if row["category"] == "web_endpoints")
    assert candidate["url"] == base + "/api/local" and candidate["verification_status"] == "candidate_only"
    foreign = [row for row in records if row["category"] == "out_of_scope_leads"]
    assert {row["relationship"] for row in foreign} == {"script_resource", "javascript_endpoint_string"}
    assert any(row.get("reason") == "max_bytes_per_file_exhausted" for row in records)
    assert any(row.get("reason") == "max_files_per_host_exhausted" for row in records)
    trace = [json.loads(line) for line in (Path(run["directory"]) / "logs/tool-calls.jsonl").read_text(encoding="utf-8").splitlines()]
    js_call = next(row for row in trace if row["params"]["url"].endswith("/a.js"))
    raw = json.loads((Path(run["directory"]) / js_call["outputs"][0]).read_text(encoding="utf-8"))
    assert len(raw["body"].encode()) == 96 and raw["truncated"]


def test_js_endpoint_verification_is_an_explicit_gap(m5_fixture):
    _, server, _ = m5_fixture
    _, run, _ = run_capability(m5_fixture, "js_analysis", {"verify_discovered_endpoints": True})
    assert run["status"] == "partial" and not server.requests
    assert run["steps"][0]["reason"] == "endpoint_verification_requires_separate_selected_web_visit"


def test_risk_checks_use_real_origin_header_and_do_not_claim_exploitation(m5_fixture):
    _, server, _ = m5_fixture
    _, run, records = run_capability(m5_fixture, "vulnerability_check", {"approved_checks": ["security_headers", "cors_policy"]})
    assert run["status"] == "completed"
    assert [row["origin"] for row in server.requests] == ["", "https://asm-origin.invalid"]
    findings = [row for row in records if row["category"] == "findings"]
    assert {row["kind"] for row in findings} == {"security_headers", "cors_policy"}
    assert all(row["status"] == "review" and row["knowledge"] == "observation" and row["evidence_ids"] for row in findings)
    cors = next(row for row in findings if row["kind"] == "cors_policy")
    assert cors["basis"]["allow_credentials"] == "true"


def test_risk_plan_request_limit_and_unknown_checks(m5_fixture):
    _, server, _ = m5_fixture
    _, _, records = run_capability(m5_fixture, "vulnerability_check", {"approved_checks": ["security_headers", "cors_policy"], "max_requests_per_host": 1})
    assert len(server.requests) == 1 and any(row.get("reason") == "max_requests_per_host_exhausted" for row in records)
    server.requests.clear()
    _, run, _ = run_capability(m5_fixture, "vulnerability_check", {"approved_checks": ["unknown_plugin"]})
    assert not server.requests and run["steps"][0]["status"] == "blocked"


def test_takeover_only_collects_approved_marker_no_dns_or_claim(m5_fixture):
    _, server, _ = m5_fixture
    _, run, records = run_capability(m5_fixture, "takeover_probe", {"approved_providers": ["GitHub Pages"]}, path="/takeover")
    assert [row["path"] for row in server.requests] == ["/takeover"]
    finding = next(row for row in records if row["category"] == "findings")
    assert finding["status"] == "review" and finding["knowledge"] == "candidate"
    assert finding["basis"]["cname_corroborated"] is False
    assert run["status"] == "completed"


def test_takeover_correlates_previously_saved_cname_evidence(m5_fixture):
    def saved_dns(ctx):
        ctx.require(network=False)
        ctx.call("dns_fixture_import", {"domain": ctx.target}, lambda: {"fixture": True})
        return result(ctx, records=[{"category": "dns_observations", "domain": "localhost", "query_type": "CNAME",
            "answers": [{"rtype": "CNAME", "value": "fixture.github.io", "accepted": True}], "evidence_ids": [ctx.last_evidence_id]}])
    _, _, records = run_capability(m5_fixture, "takeover_probe", {"approved_providers": ["GitHub Pages"]},
        path="/takeover", extras=["dns_recursive"], adapters={"dns_recursive": saved_dns})
    finding = next(row for row in records if row["category"] == "findings")
    assert finding["basis"]["cname_matches"] == ["fixture.github.io"] and len(finding["evidence_ids"]) == 2


@pytest.mark.parametrize("providers,status", [([], "skipped"), (["unknown"], "blocked")])
def test_takeover_allowlist_has_no_request_when_empty_or_invalid(m5_fixture, providers, status):
    _, server, _ = m5_fixture
    _, run, _ = run_capability(m5_fixture, "takeover_probe", {"approved_providers": providers})
    assert not server.requests and run["steps"][0]["status"] == status


def test_auth_anonymous_plan_reports_denial_candidate_and_inconclusive(m5_fixture):
    _, server, _ = m5_fixture
    _, run, records = run_capability(m5_fixture, "auth_audit", {"approved_checks": ["anonymous_protected_paths"],
        "protected_paths": ["/private", "/open", "/missing", "/open"]})
    assert [row["path"] for row in server.requests] == ["/private", "/open", "/missing"]
    assert run["status"] == "completed"
    finding = next(row for row in records if row["category"] == "findings")
    assert finding["kind"] == "anonymous_access_candidate" and finding["status"] == "review"
    assert any(row.get("reason") == "configured_denial_status_observed" for row in records)
    assert any(row.get("reason") == "response_not_success_or_configured_denial" for row in records)


@pytest.mark.parametrize("params", [{"approved_checks": ["unknown_login_check"]},
    {"approved_checks": ["anonymous_protected_paths"], "protected_paths": ["//192.0.2.29/path"]},
    {"approved_checks": ["anonymous_protected_paths"]}])
def test_auth_requires_explicit_valid_check_plan_before_requests(m5_fixture, params):
    _, server, _ = m5_fixture
    _, run, _ = run_capability(m5_fixture, "auth_audit", params)
    assert not server.requests and run["steps"][0]["status"] == "blocked"


def test_auth_login_redirect_is_not_an_anonymous_access_finding(m5_fixture):
    _, server, _ = m5_fixture
    _, _, records = run_capability(m5_fixture, "auth_audit", {"approved_checks": ["anonymous_protected_paths"],
        "protected_paths": ["/private-redirect"]})
    assert [row["path"] for row in server.requests] == ["/private-redirect", "/login"]
    assert not any(row["category"] == "findings" for row in records)
    assert any(row.get("reason") == "redirected_response_requires_review" for row in records)


def test_native_m5_replay_has_no_live_fallback(m5_fixture):
    _, server, _ = m5_fixture
    _, run, _ = run_capability(m5_fixture, "web_crawl", source="replay")
    assert not server.requests and run["steps"][0]["status"] == "blocked"


def test_crawler_pause_resume_reuses_completed_http_evidence(m5_fixture, monkeypatch):
    _, server, _ = m5_fixture
    original_http = ExecutionContext.http
    paused = []
    def pause_after_first(ctx, *args, **kwargs):
        reply = original_http(ctx, *args, **kwargs)
        if not paused:
            paused.append(ctx.run["run_id"])
            ctx.workbench.control(ctx.run["run_id"], "pause")
        return reply
    monkeypatch.setattr(ExecutionContext, "http", pause_after_first)
    wb, run, _ = run_capability(m5_fixture, "web_crawl", {"max_depth": 2, "max_urls_per_host": 10})
    assert run["status"] == "paused" and [row["path"] for row in server.requests] == ["/"]
    resumed = wb.resume(run["run_id"], background=False)
    assert resumed["status"] == "completed" and resumed["run_id"] == run["run_id"]
    assert [row["path"] for row in server.requests] == ["/", "/child", "/grand"]


def test_crawler_rechecks_permission_before_next_real_request(m5_fixture, monkeypatch):
    _, server, _ = m5_fixture
    original_http = ExecutionContext.http
    revoked = []
    def revoke_after_first(ctx, *args, **kwargs):
        reply = original_http(ctx, *args, **kwargs)
        if not revoked:
            revoked.append(True)
            config = ctx.workbench.project(ctx.run["project_id"])["config"]
            config["permissions"]["web_crawl"]["allow"] = False
            ctx.workbench.save_project(config, project_id=ctx.run["project_id"])
        return reply
    monkeypatch.setattr(ExecutionContext, "http", revoke_after_first)
    _, _, records = run_capability(m5_fixture, "web_crawl", {"max_depth": 2, "max_urls_per_host": 10})
    assert [row["path"] for row in server.requests] == ["/"]
    assert any(row.get("reason") == "function_permission_denied" for row in records)


def test_js_upgrade_reuses_existing_larger_file_receipt(m5_fixture):
    _, server, base = m5_fixture
    def old_js(ctx):
        ctx.http(ctx.target)
        ctx.http(base + "/a.js")
        raise KeyboardInterrupt
    root, _, _ = m5_fixture
    with pytest.raises(KeyboardInterrupt):
        run_capability(m5_fixture, "js_analysis", {"max_files_per_host": 1, "max_bytes_per_file": 96},
            adapters={"js_analysis": old_js})
    wb = Workbench(root, recover=False)
    run_id = wb.store.rows("SELECT id FROM runs")[0]["id"]
    run = wb.resume(run_id, background=False)
    assert run["status"] == "completed" and [row["path"] for row in server.requests] == ["/", "/a.js"]
    records = [json.loads(row["data"]) for row in wb.store.rows("SELECT data FROM records WHERE run=?", (run_id,))]
    assert any(row.get("reason") == "max_bytes_per_file_exhausted" for row in records)


def test_http_strict_one_request_blocks_redirect_without_transmitting(m5_fixture):
    _, server, _ = m5_fixture
    wb, run, _ = run_capability(m5_fixture, "web_visit", {"max_requests_per_host": 1}, path="/private-redirect")
    assert [row["path"] for row in server.requests] == ["/private-redirect"]
    assert run["status"] == "partial" and run["steps"][0]["status"] == "quota-exhausted"
    events = wb.store.events(run["run_id"])
    assert len([row for row in events if row["kind"] == "physical_request_started"]) == 1
    assert len([row for row in events if row["kind"] == "physical_request_blocked"]) == 1
    assert [row["data"]["status"] for row in events if row["kind"] == "tool_call"] == ["completed", "quota-exhausted"]


def test_http_budget_is_shared_across_steps_on_same_host(m5_fixture):
    _, server, base = m5_fixture
    wb, run, _ = run_capability(m5_fixture, "web_visit", {"max_requests_per_host": 1, "urls": [base + "/", base + "/child"]})
    assert [row["path"] for row in server.requests] == ["/"]
    assert [row["status"] for row in run["steps"]] == ["completed", "quota-exhausted"]
    assert run["status"] == "partial"
    assert sum(row["kind"] == "physical_request_started" for row in wb.store.events(run["run_id"])) == 1


def test_pause_restart_keeps_physical_budget_and_cached_actions(m5_fixture, monkeypatch):
    root, server, _ = m5_fixture
    original_http = ExecutionContext.http
    paused = []
    def pause_after_first(ctx, *args, **kwargs):
        reply = original_http(ctx, *args, **kwargs)
        if not paused:
            paused.append(True)
            ctx.workbench.control(ctx.run["run_id"], "pause")
        return reply
    monkeypatch.setattr(ExecutionContext, "http", pause_after_first)
    _, run, _ = run_capability(m5_fixture, "web_crawl", {"max_requests_per_host": 2, "max_depth": 2, "max_urls_per_host": 10})
    assert run["status"] == "paused" and len(server.requests) == 1
    wb = Workbench(root, recover=False)
    resumed = wb.resume(run["run_id"], background=False)
    assert resumed["run_id"] == run["run_id"] and resumed["status"] == "partial"
    assert [row["path"] for row in server.requests] == ["/", "/child"]
    reservations = [row for row in wb.store.events(run["run_id"]) if row["kind"] == "physical_request_started"]
    assert [row["data"]["used"] for row in reservations] == [1, 2]


def test_failed_physical_attempt_is_not_refunded(m5_fixture):
    _, server, base = m5_fixture
    def adapter(ctx):
        with pytest.raises(httpx.HTTPError):
            ctx.http(base + "/disconnect")
        ctx.http(base + "/open")
    wb, run, _ = run_capability(m5_fixture, "web_visit", {"max_requests_per_host": 1}, adapters={"web_visit": adapter})
    assert [row["path"] for row in server.requests] == ["/disconnect"]
    assert run["status"] == "partial" and run["steps"][0]["status"] == "quota-exhausted"
    assert sum(row["kind"] == "physical_request_started" for row in wb.store.events(run["run_id"])) == 1


def test_parallel_contexts_use_one_authoritative_http_allowance(m5_fixture):
    root, server, base = m5_fixture
    def adapter(parent):
        peers = [Workbench(root, recover=False), Workbench(root, recover=False)]
        gate = threading.Barrier(2)
        def request(index):
            child = ExecutionContext(peers[index], parent.run, parent.step)
            gate.wait(timeout=5)
            try:
                child.http(base + "/open?worker=" + str(index))
                return "completed", child.records
            except PolicyDenied as exc:
                assert str(exc) == "http_request_budget_exhausted"
                return "budget-denied", child.records
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(request, range(2)))
        assert sorted(status for status, _ in outcomes) == ["budget-denied", "completed"]
        return result(parent, records=[row for _, rows in outcomes for row in rows], status="partial", reason="fixture_parallel_budget_check")
    wb, run, _ = run_capability(m5_fixture, "web_visit", {"max_requests_per_host": 1}, adapters={"web_visit": adapter})
    assert len(server.requests) == 1 and run["status"] == "partial"
    assert sum(row["kind"] == "physical_request_started" for row in wb.store.events(run["run_id"])) == 1


def test_parallel_contexts_reserve_tool_calls_atomically(m5_fixture):
    def adapter(parent):
        gate = threading.Barrier(2)
        def operation(index):
            child = ExecutionContext(parent.workbench, parent.run, parent.step)
            gate.wait(timeout=5)
            try:
                child.call("fixture_operation", {"index": index}, lambda: {"fixture": index})
                return "completed", child.records
            except PolicyDenied as exc:
                assert str(exc) == "tool_call_budget_exhausted"
                return "budget-denied", child.records
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(operation, range(2)))
        assert sorted(status for status, _ in outcomes) == ["budget-denied", "completed"]
        return result(parent, records=[row for _, rows in outcomes for row in rows], status="partial", reason="fixture_tool_budget_check")
    wb, run, _ = run_capability(m5_fixture, "web_visit", adapters={"web_visit": adapter},
        budget={"per_tool": {"web_visit": {"max_calls": 1}}})
    assert sum(row["kind"] == "tool_started" for row in wb.store.events(run["run_id"])) == 1


def test_screenshot_real_browser_http_budget_retains_partial_png(m5_fixture):
    _, server, _ = m5_fixture
    wb, run, records = run_capability(m5_fixture, "screenshot", {"max_requests_per_host": 1})
    assert [row["path"] for row in server.requests] == ["/"]
    assert run["status"] == "partial" and run["steps"][0]["reason"] == "browser_requests_blocked"
    image = next(row for row in records if row.get("kind") == "screenshot")
    assert (Path(run["directory"]) / image["path"]).read_bytes().startswith(b"\x89PNG")
    events = wb.store.events(run["run_id"])
    assert sum(row["kind"] == "physical_request_started" for row in events) == 1
    assert any(row["kind"] == "physical_request_blocked" for row in events)


def test_permission_recheck_after_durable_reservation_prevents_send(m5_fixture, monkeypatch):
    _, server, _ = m5_fixture
    original_reserve = ExecutionContext.reserve_http_request
    def revoke_after_reserve(ctx, *args, **kwargs):
        original_reserve(ctx, *args, **kwargs)
        config = ctx.workbench.project(ctx.run["project_id"])["config"]
        config["permissions"]["web_visit"]["allow"] = False
        ctx.workbench.save_project(config, project_id=ctx.run["project_id"])
    monkeypatch.setattr(ExecutionContext, "reserve_http_request", revoke_after_reserve)
    wb, run, _ = run_capability(m5_fixture, "web_visit", {"max_requests_per_host": 1})
    assert not server.requests and run["steps"][0]["status"] == "skipped"
    assert sum(row["kind"] == "physical_request_started" for row in wb.store.events(run["run_id"])) == 1


def test_pre_ledger_http_attempts_are_not_reset_when_resuming(m5_fixture, monkeypatch):
    root, server, _ = m5_fixture
    original_http = ExecutionContext.http
    paused = []
    def pause_after_first(ctx, *args, **kwargs):
        reply = original_http(ctx, *args, **kwargs)
        if not paused:
            paused.append(True)
            ctx.workbench.control(ctx.run["run_id"], "pause")
        return reply
    monkeypatch.setattr(ExecutionContext, "http", pause_after_first)
    wb, run, _ = run_capability(m5_fixture, "web_crawl", {"max_requests_per_host": 1})
    assert run["status"] == "paused" and len(server.requests) == 1
    # Model a historical interrupted run from before this request-ledger upgrade.
    with wb.store.connection() as conn:
        conn.execute("DELETE FROM events WHERE run=? AND kind='physical_request_started'", (run["run_id"],))
        for row in conn.execute("SELECT id,data FROM events WHERE run=? AND kind='tool_started'", (run["run_id"],)).fetchall():
            data = json.loads(row["data"])
            data.pop("request_ledger_version", None)
            conn.execute("UPDATE events SET data=? WHERE id=?", (json.dumps(data), row["id"]))
    restarted = Workbench(root, recover=False)
    resumed = restarted.resume(run["run_id"], background=False)
    assert resumed["status"] == "partial" and len(server.requests) == 1
    blocked = next(row for row in restarted.store.events(run["run_id"]) if row["kind"] == "physical_request_blocked")
    assert blocked["data"]["legacy_assumed_attempts"] == 1 and blocked["data"]["used"] == 1


@pytest.mark.parametrize("capability,tool", [("company_lookup", "stage_2a"), ("search", "fofa"),
    ("osint", "stage_p1"), ("passive_supply_chain", "stage_p2")])
def test_single_label_company_requires_typed_scope_approval(m5_fixture, capability, tool):
    root, server, _ = m5_fixture
    calls = []
    def adapter(ctx):
        ctx.require(network=False)
        calls.append(ctx.target)
        return result(ctx)
    config = {"schema_version": 2, "profile": "typed_fixture", "mode_preset": "passive_discovery",
        "execution": {"source": "live"}, "targets": {"roots": ["FixtureCo"], "company": "FixtureCo"},
        "scope_sets": {"investigation": {"include": ["FixtureCo"], "subjects": [], "exclude": []}},
        "permissions": {capability: {"allow": True, "scope_ref": "investigation"}},
        "plan": {"selection": "custom", "selected_capabilities": [capability], "selected_tools": [tool]},
        "budgets": {"max_rounds": 1, "max_duration_seconds": 60}}
    wb = Workbench(root, adapters={capability: adapter}, recover=False)
    wb.save_project(config)
    denied = wb.start("typed_fixture", background=False)
    assert not calls and denied["steps"][0]["status"] == "skipped"
    config["scope_sets"]["investigation"]["subjects"] = ["FixtureCo"]
    wb.save_project(config)
    allowed = wb.start("typed_fixture", background=False)
    assert calls == ["FixtureCo"] and allowed["status"] == "completed" and not server.requests


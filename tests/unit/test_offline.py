"""N10 regression: replay cannot reach DNS, sockets, HTTP, browsers or WSL."""
import base64
import json
import socket
import subprocess
import sys
from types import SimpleNamespace

import dns.resolver
import httpx
import pytest

from asm.conf import Config
from asm.db import Database
from asm.models import Domain
from asm.offline import OfflineBridge, OfflineExecutionError, OfflineJobs, ReplayHTTP
from asm.pipeline import STAGES, StageContext, run_pipeline
from asm.scope import Scope, ScopeError
from asm.stages import s5_dns_cdn, s7_web
from asm.utils.constants import LEAK_PATHS, SPRAY_PATHS
from asm.utils.dns import DNSSettings


@pytest.fixture
def no_external_io(monkeypatch):
    attempts = []
    def blocked(*args, **kwargs):
        attempts.append("external_io")
        raise AssertionError("Offline replay attempted external I/O")
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
        monkeypatch.setattr(socket, name, blocked)
    for name in ("connect", "connect_ex", "sendto", "sendall"):
        monkeypatch.setattr(socket.socket, name, blocked)
    monkeypatch.setattr(dns.resolver.Resolver, "resolve", blocked)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=blocked))
    yield attempts
    assert attempts == []


def fixture_config(tmp_path, project, *, missing=False, source="live"):
    base = "http://127.0.0.1:8765"
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jI9sAAAAASUVORK5CYII=")
    (tmp_path / "saved.png").write_bytes(png)
    entries = [{"url": base, "status": 200, "body": "<title>Saved fixture portal</title>"},
               {"url": base + "/asm-missing-*", "status": 404, "body": "Missing"}]
    if not missing:
        paths = set(SPRAY_PATHS + LEAK_PATHS + ["/api/v1/user", "/mobile/v1/x"])
        entries.extend({"url": base + path, "status": 404, "body": "Missing"} for path in sorted(paths))
        entries.append({"url": base + "/saved-private", "status": 200, "body": "Saved private path"})
        next(row for row in entries if row["url"] == base + "/robots.txt").update(
            status=200, body="Disallow: /saved-private")
        next(row for row in entries if row["url"] == base + "/admin").update(
            status=200, body="<title>Saved login page</title><input type='password'>")
    (tmp_path / "web.json").write_text(json.dumps({"responses": entries,
        "screenshots": {base: "saved.png"}}), encoding="utf-8")
    # Other legacy fixture paths remain available without accessing project secrets.
    fixtures = tmp_path / "tests/fixtures"
    fixtures.mkdir(parents=True)
    for filename in ("equity.json", "icp.json", "subdomains.json", "dns.json", "sourcegraph.sse", "tender.txt"):
        (fixtures / filename).write_bytes((project / "tests/fixtures" / filename).read_bytes())
    data = {"profile": "offline_fixture", "authorization": True,
        "targets": {"company": "Fixture Example Organization", "roots": ["localhost"],
                    "ip_cidrs": ["127.0.0.1/32"]},
        "ports": {"targets": ["127.0.0.1"], "tcp": "8765"},
        "web": {"urls": [base], "screenshots": True}, "replay": {"web_file": "web.json"},
        "execution": {"source": source}, "dns": {"takeover_probe": True},
        "oneforall": {"enabled": True}, "osint": {"keywords": ["localhost.example.invalid"]},
        "output": {"dir": "output"}}
    return Config(data, tmp_path / "fixture.yaml", tmp_path)


def context(config, db, output):
    return StageContext(config, db, OfflineBridge(), OfflineJobs(), Scope(config.data),
                        output / "stages/7", dry_run=True)


def test_stage7_replays_http_paths_and_png_without_external_io(tmp_path, project, db, no_external_io):
    config = fixture_config(tmp_path, project)
    ctx = context(config, db, tmp_path / "delivery")
    result = s7_web.run(ctx)
    assert result.status == "completed" and result.count == 3
    urls = db.rows("SELECT url,screenshot FROM urls")
    assert {row["url"] for row in urls} == {
        "http://127.0.0.1:8765", "http://127.0.0.1:8765/admin",
        "http://127.0.0.1:8765/robots.txt", "http://127.0.0.1:8765/saved-private"}
    png = ctx.stage_dir.parent.parent / "screenshots/asset-1.png"
    assert png.read_bytes() == (tmp_path / "saved.png").read_bytes()
    evidence = json.loads((ctx.stage_dir / "web-replay-evidence.json").read_text(encoding="utf-8"))
    assert evidence["execution_source"] == "replay" and evidence["screenshots"][0]["sha256"]
    assert all(row["status"] == "replayed" for row in evidence["requests"])
    assert db.rows("SELECT source FROM assets")[0]["source"] == "fixture_http"
    assert not no_external_io


def test_missing_web_evidence_is_partial_without_live_fallback(tmp_path, project, db, no_external_io):
    config = fixture_config(tmp_path, project, missing=True)
    ctx = context(config, db, tmp_path / "delivery")
    result = s7_web.run(ctx)
    assert result.status == "partial" and "no saved evidence" in result.notes[-1]
    assert db.rows("SELECT kind FROM findings WHERE kind='request_error'")
    assert not no_external_io


def test_replay_redirect_checks_scope_before_following(tmp_path, project, db, no_external_io):
    config = fixture_config(tmp_path, project)
    path = tmp_path / "web.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["responses"][0].update(status=302, headers={"location": "http://outside.example.invalid"})
    path.write_text(json.dumps(saved), encoding="utf-8")
    client = ReplayHTTP(context(config, db, tmp_path / "delivery"))
    try:
        with pytest.raises(ScopeError, match="Out of scope"):
            client.get("http://127.0.0.1:8765")
        assert len(client.requests) == 1
    finally:
        client.close()


def test_direct_screenshot_helper_uses_replay_without_browser(tmp_path, project, db, no_external_io):
    config = fixture_config(tmp_path, project)
    ctx = context(config, db, tmp_path / "delivery")
    path = s7_web.screenshot(ctx, "http://127.0.0.1:8765", 99)
    assert path.is_file()


def test_dry_run_takeover_is_not_dispatched(tmp_path, project, db, no_external_io, monkeypatch):
    config = fixture_config(tmp_path, project)
    ctx = context(config, db, tmp_path / "delivery")
    db.domain(Domain("localhost", sources="fixture"))
    calls = []
    original = s5_dns_cdn.probe_takeover
    monkeypatch.setattr(s5_dns_cdn, "probe_takeover", lambda *args: calls.append(args))
    observations = [{"domain": "localhost", "source": "fixture", "resolver": "fixture",
        "kind": "cname_chain", "chain": ["dangling.example.invalid"],
        "terminal": "dangling.example.invalid", "status": "complete"}]
    s5_dns_cdn.ingest(ctx, observations, DNSSettings.from_config(config.data), [])
    assert calls == []
    # A helper invoked outside ingest must also preserve the boundary.
    original(ctx, "localhost", "dangling.example.invalid")


@pytest.mark.parametrize("source,flag", [("live", True), ("replay", False)])
def test_entire_pipeline_and_resume_are_offline(tmp_path, project, monkeypatch, no_external_io, source, flag):
    config = fixture_config(tmp_path, project, source=source)
    load_flags = []
    def load(profile, root, *, load_secrets=True):
        load_flags.append(load_secrets)
        return config
    monkeypatch.setattr("asm.pipeline.load_config", load)
    monkeypatch.setenv("FOFA_KEY", "fixture_only_unused_key")
    result = run_pipeline("fixture", list(STAGES), root=tmp_path, dry_run=flag)
    assert all(item["status"] == "completed" for item in result.values()), result
    output = config.output / "dry-run"
    with Database(output / "asm.db") as db:
        db.upsert("jobs", {"jobid": "interrupted-live-job", "stage": "6", "tool": "nmap",
                           "status": "running"}, ("jobid",))
        count = db.rows("SELECT COUNT(*) AS count FROM assets")[0]["count"]
    resumed = run_pipeline("fixture", list(STAGES), root=tmp_path, dry_run=flag, resume=True)
    assert all(item["status"] == "skipped" for item in resumed.values())
    with Database(output / "asm.db") as db:
        assert db.rows("SELECT COUNT(*) AS count FROM assets")[0]["count"] == count
        assert db.rows("SELECT status FROM jobs")[0]["status"] == "running"
    if flag:
        assert load_flags == [False, False]
    assert not no_external_io


def test_offline_tool_services_fail_before_dispatch(no_external_io):
    bridge, jobs = OfflineBridge(), OfflineJobs()
    for action in (lambda: bridge.control("echo x"), lambda: bridge.workspace,
                   lambda: jobs.run("nmap", stage="6"), lambda: jobs.fs):
        with pytest.raises(OfflineExecutionError):
            action()
    assert jobs.recover() == [] and jobs.wait_all() == []


def test_legacy_pipeline_rejects_schema2_live_permissions_bypass(tmp_path, project, monkeypatch, no_external_io):
    config = fixture_config(tmp_path, project, source="live")
    config.data["schema_version"] = 2
    monkeypatch.setattr("asm.pipeline.load_config", lambda *args, **kwargs: config)
    with pytest.raises(ScopeError, match="workbench-run"):
        run_pipeline("fixture", ["6", "7"], root=tmp_path)
    assert not config.output.exists()

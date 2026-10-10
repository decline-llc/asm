import importlib.util
import json
import sys
import threading
from types import SimpleNamespace

import pytest
import requests

from asm.scope import Scope
from asm.stages import oneforall
from asm.utils import oneforall as support


@pytest.fixture
def runner(project, monkeypatch):
    monkeypatch.setitem(sys.modules, "oneforall_support", support)
    spec = importlib.util.spec_from_file_location("oneforall_runner_test", project / "tools/oneforall_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configuration_and_effective_resume_defaults(project):
    from asm.conf import load_config
    config = load_config("demo", project)
    assert config.data["oneforall"] == support.OneForAllSettings().as_config()
    previous = config.fingerprint()
    config.data["oneforall"]["enabled"] = False
    assert config.fingerprint() != previous
    for values in ({"enabled": "false"}, {"modules": []}, {"modules": ["modules.check.cdx"]},
                   {"modules": ["modules.search.fofa_api"]}, {"dns": True}, {"module_timeout": True},
                   {"request_timeout": -1}, {"request_timeout": 61}):
        with pytest.raises(ValueError):
            support.OneForAllSettings.from_config({"oneforall": values})
    for value in ("192.0.2.1", "https://ops.example.invalid/", "ops.example.invalid:443", "a..example.invalid"):
        with pytest.raises(ValueError):
            support.domain_name(value)


def context(db, directory):
    scope = Scope({"targets": {"roots": ["ops.example.invalid", "example.invalid"]},
                   "scope": {"exclude_saas": ["blocked.ops.example.invalid"]}}, passive_only=True)
    return SimpleNamespace(db=db, scope=scope, jobs=SimpleNamespace(wait=lambda h: h, result_dir=lambda h: directory),
        note=lambda kind, target, evidence: db.finding({"kind": kind, "url": target, "evidence": evidence, "status": "review"}))


def write_output(directory, rows, **changes):
    report = {"root": "ops.example.invalid", "mode": "passive", "status": "completed",
              "flags": dict.fromkeys(support.PASSIVE_FLAGS, False), **changes}
    (directory / "oneforall-run.json").write_text(json.dumps(report))
    (directory / "oneforall-observations.json").write_text(json.dumps(rows))


def test_source_merge_scope_and_unverified_ips(db, tmp_path):
    rows = [{"subdomain": "api.ops.example.invalid", "source": source, "ip": "198.18.0.9", "port": 80}
            for source in ("CrtshQuery", "CertSpotterQuery")]
    rows += [{"subdomain": "*.wild.ops.example.invalid", "source": "CrtshQuery"},
             {"subdomain": "api.example.invalid", "source": "CrtshQuery"},
             {"subdomain": "blocked.ops.example.invalid", "source": "CrtshQuery"},
             {"subdomain": "ops.example.invalid.evil", "source": "CrtshQuery"},
             {"subdomain": "https://api.ops.example.invalid", "source": "CrtshQuery"},
             {"subdomain": "bad.ops.example.invalid", "source": "=untrusted"}, {"subdomain": None, "source": "Empty"}]
    write_output(tmp_path, rows)
    ctx = context(db, tmp_path)
    accepted, notes = oneforall.ingest(ctx, "ops.example.invalid", SimpleNamespace(rc=0, jobid="fixture"))
    assert len(accepted) == 3 and notes
    domains = db.rows("SELECT domain,sources FROM domains ORDER BY domain")
    assert len(domains) == 2 and domains[0]["sources"] == "oneforall:CertSpotterQuery,oneforall:CrtshQuery"
    evidence = db.get_fact("oneforall:ops.example.invalid")
    assert len(evidence["excluded"]) == 3 and len(evidence["invalid"]) == 2
    assert db.rows("SELECT * FROM assets") == [] and db.rows("SELECT * FROM dns_records") == []


def test_failure_empty_and_malformed_are_distinct(db, tmp_path):
    handle = SimpleNamespace(rc=0, jobid="fixture")
    ctx = context(db, tmp_path)
    write_output(tmp_path, [])
    assert oneforall.ingest(ctx, "ops.example.invalid", handle) == ([], [])
    write_output(tmp_path, [{"subdomain": "api.ops.example.invalid", "source": "CrtshQuery"}], status="partial")
    handle.rc = 2
    accepted, notes = oneforall.ingest(ctx, "ops.example.invalid", handle)
    assert len(accepted) == 1 and notes
    write_output(tmp_path, {"unexpected": []})
    assert oneforall.ingest(ctx, "ops.example.invalid", handle)[1]
    write_output(tmp_path, [], flags={"req": False})
    assert oneforall.ingest(ctx, "ops.example.invalid", handle)[1]
    (tmp_path / "oneforall-observations.json").unlink()
    handle.rc = 124
    assert oneforall.ingest(ctx, "ops.example.invalid", handle)[1]
    assert db.get_fact("oneforall:ops.example.invalid")["status"] == "partial"


def test_http_provider_guard_redirect_and_body_limit(runner, monkeypatch):
    options = support.OneForAllSettings(modules=("modules.certificates.certspotter",))
    states = {options.modules[0]: {"errors": []}}
    events, calls = [], []
    status, body = 200, b"fixture"
    def request(session, method, url, **kwargs):
        calls.append((url, kwargs))
        reply = requests.Response()
        reply.status_code, reply.url = status, url
        reply._content, reply._content_consumed = body, True
        return reply
    monkeypatch.setattr(requests.sessions.Session, "request", request)
    monkeypatch.setattr(runner, "BODY_LIMIT", 16)
    runner.install_http_guard(options, states, events, threading.Lock())
    thread, previous_name = threading.current_thread(), threading.current_thread().name
    thread.name = "certspotter"
    try:
        with requests.Session() as session:
            assert session.get("https://api.certspotter.com/v1/issuances").content == b"fixture"
            assert calls[0][1]["allow_redirects"] is False and calls[0][1]["verify"] is True
            with pytest.raises(ValueError):
                session.get("https://ops.example.invalid/")
            assert len(calls) == 1
            status = 302
            with pytest.raises(ValueError):
                session.get("https://api.certspotter.com/redirect")
            status, body = 200, b"x" * 17
            with pytest.raises(ValueError):
                session.get("https://api.certspotter.com/oversized")
            assert len(states[options.modules[0]]["errors"]) == 3
    finally:
        thread.name = previous_name


def test_stage4_schedules_and_merges_passive_sources(db, tmp_path, project, monkeypatch):
    import httpx
    from asm.conf import Config
    from asm.pipeline import StageContext
    from asm.stages import s4_subdomain
    monkeypatch.delenv("FOFA_KEY", raising=False)
    monkeypatch.delenv("QUAKE_TOKEN", raising=False)
    calls = []
    write_output(tmp_path, [{"subdomain": "api.ops.example.invalid", "source": "CertSpotterQuery"}])
    (tmp_path / "subdomains.txt").write_text("api.ops.example.invalid\napi.example.invalid\n")

    def run(tool, args, **kwargs):
        calls.append((tool, kwargs))
        return SimpleNamespace(rc=0, jobid="fixture")
    jobs = SimpleNamespace(run=run, wait=lambda h: h, result_dir=lambda h: tmp_path)
    client = httpx.Client

    def response(request):
        assert request.url.host in {"crt.sh", "api.hackertarget.com", "web.archive.org"}
        if request.url.host == "crt.sh":
            return httpx.Response(200, json=[{"name_value": "api.ops.example.invalid"}])
        if request.url.host == "web.archive.org":
            return httpx.Response(200, json=[["original"], ["https://api.ops.example.invalid/"]])
        return httpx.Response(200, text="api.ops.example.invalid,192.0.2.5")
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=httpx.MockTransport(response), **kwargs))
    monkeypatch.setattr(s4_subdomain, "enumerate_dns", lambda *a, **k: pytest.fail("Passive mode queried target DNS"))
    scope = Scope({"authorization": True, "targets": {"roots": ["ops.example.invalid"]}}, passive_only=True)
    ctx = StageContext(Config({}, project / "profiles/test.yaml", project), db,
        SimpleNamespace(workspace="/home/test/asm-ws"), jobs, scope, tmp_path / "stage4", passive_only=True)
    result = s4_subdomain.run(ctx)
    assert result.status == "completed" and result.count == 5
    assert len(calls) == 2 and calls[0][0].endswith("OneForAll/.venv/bin/python")
    assert calls[0][1]["background"] is True and calls[1][0] == "subfinder"
    rows = db.rows("SELECT domain,sources FROM domains")
    assert len(rows) == 1 and len(rows[0]["sources"].split(",")) == 5
    assert (ctx.stage_dir / "oneforall-evidence.json").is_file()


@pytest.mark.parametrize("dry_run,target_local", [(True, False), (False, True)])
def test_stage4_offline_modes_never_start_collectors(db, tmp_path, project, dry_run, target_local):
    from asm.conf import Config
    from asm.pipeline import StageContext
    from asm.stages import s4_subdomain
    scope = Scope({"targets": {"roots": ["example.invalid"]}}, passive_only=True)
    ctx = StageContext(Config({}, project / "profiles/test.yaml", project), db, None, None, scope, tmp_path,
                       passive_only=True, dry_run=dry_run, target_local=target_local)
    assert s4_subdomain.run(ctx).status == "completed"

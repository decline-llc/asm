import os
import json
import shutil
import sys
import time
from contextlib import contextmanager

import pytest

from asm.bridge import Bridge, JobManager, WsFs
from asm.conf import Config
from asm.models import Domain
from asm.pipeline import StageContext
from asm.scope import Scope

pytestmark = pytest.mark.wsl


@pytest.fixture
def bridge():
    if sys.platform != "win32" or not shutil.which("wsl.exe") or os.getenv("ASM_TEST_WSL") != "1":
        pytest.skip("Set ASM_TEST_WSL=1 on Windows for real WSL tests")
    from dotenv import load_dotenv
    load_dotenv()
    value = Bridge()
    value.control("true")
    return value


def test_background_completion_failure_and_tar(bridge, db, tmp_path):
    # A direct control call also works when inherited Windows PATH has spaces/parentheses.
    assert bridge.control(bridge.command("python3", ["-c", "print('direct-ok')"])).stdout.strip() == b"direct-ok"
    jobs = JobManager(bridge, db, tmp_path, foreground_seconds=0.1, poll_seconds=0.05)
    first = jobs.run("python3", ["-c", "import time; time.sleep(.5); open('result.bin','wb').write(bytes(range(256)))"],
                     stage="test", timeout=10)
    second = jobs.run("python3", ["-c", "raise SystemExit(7)"], stage="test", timeout=10, background=True)
    assert first.status == "running"
    jobs.wait_all(max_seconds=20)
    assert first.status == "completed" and second.status == "failed" and second.rc == 7
    assert (jobs.result_dir(first) / "result.bin").read_bytes() == bytes(range(256))
    assert WsFs(bridge).exists(second.directory + "/done")


def test_root_nmap_native_loopback(bridge, db, tmp_path, project):
    jobs = JobManager(bridge, db, tmp_path, poll_seconds=0.1)
    source = (project / "tests/fixtures/server.py").read_text(encoding="utf-8")
    # Put a bounded fixture and its listeners in WSL. Windows localhost is a different host under NAT.
    server = jobs.run("python3", ["{job}/server.py", "--port", "18765", "--extra-listeners"],
                      stage="harness", timeout=35, background=True, inputs={"server.py": source})
    import time
    time.sleep(1)
    nmap = jobs.run("nmap", ["-sS", "-sU", "-Pn", "-n", "-p", "T:18765,8766,8768,U:8767",
                              "--max-retries", "0", "-oX", "{job}/nmap.xml", "127.0.0.1"],
                    stage="test", timeout=20, root=True)
    jobs.wait(nmap, max_seconds=25)
    assert nmap.rc == 0
    from asm.stages.s6_port import parse_nmap
    ports = {(r.port, r.proto) for r in parse_nmap(jobs.result_dir(nmap) / "nmap.xml")}
    assert {(18765, "tcp"), (8766, "tcp"), (8768, "tcp"), (8767, "udp")} <= ports
    # Stop only the recorded fixture process; wait_all records the terminating exit code.
    bridge.control("kill " + WsFs(bridge).read_text(server.directory + "/pid").strip(), check=False)


@contextmanager
def dns_servers(bridge, jobs, project, records):
    source = (project / "tests/fixtures/dns_server.py").read_text(encoding="utf-8")
    server = jobs.run("python3", ["{job}/dns_server.py", "--records", "{job}/records.json", "--lifetime", "45"],
        stage="harness", timeout=50, background=True, inputs={"dns_server.py": source, "records.json": json.dumps(records)})
    fs = WsFs(bridge)
    try:
        deadline = time.monotonic() + 8
        while not fs.exists(server.directory + "/ready.json"):
            assert time.monotonic() < deadline, "Native DNS fixture failed to start"
            time.sleep(0.1)
        yield [f"127.0.0.1:{port}" for port in json.loads(fs.read_text(server.directory + "/ready.json"))]
    finally:
        if fs.exists(server.directory + "/pid"):
            pid = fs.read_text(server.directory + "/pid").strip()
            assert pid.isdigit()
            bridge.control("kill " + pid, check=False)
        jobs.wait(server, max_seconds=10)


def dns_context(bridge, db, jobs, tmp_path, project, resolvers, **settings):
    data = {"profile": "dns-test", "dns": {"resolvers": resolvers, "preferred_resolver": resolvers[len(resolvers) // 2],
            "windows_verify": False, "timeout": 1, "workers": 6, **settings}, "limits": {"dns_timeout": 30}}
    scope = Scope({"authorization": True, "targets": {"roots": ["example.invalid"],
                  "ip_cidrs": ["192.0.2.0/24", "2001:db8::/32"]}}, passive_only=True)
    return StageContext(Config(data, project / "profiles/test.yaml", project), db, bridge, jobs, scope,
                        tmp_path / "stage5", passive_only=True)


def test_dnsx_dig_resolver_correction_and_cname_terminal(bridge, db, tmp_path, project):
    from asm.stages import s5_dns_cdn
    from asm.stages.s6_port import selected_targets
    db.domain(Domain("app.example.invalid"))
    jobs = JobManager(bridge, db, tmp_path, poll_seconds=0.1)
    records = [{"app.example.invalid": {"A": [address], "AAAA": ["2001:db8::20"],
        "MX": ["10 mail.example.invalid"], "NS": ["ns1.example.invalid"], "CNAME": ["edge.other.invalid"]},
        "edge.other.invalid": {"CNAME": ["fixture.gccdn.net"]}, "fixture.gccdn.net": {"A": [address]}}
        for address in ("0.0.0.0", "192.0.2.20", "198.18.0.8")]
    with dns_servers(bridge, jobs, project, records) as resolvers:
        ctx = dns_context(bridge, db, jobs, tmp_path, project, resolvers)
        result = s5_dns_cdn.run(ctx)
        assert result.status == "completed", result.notes
        evidence = db.get_fact("dns:app.example.invalid")
        assert evidence["selected"] == {"A": ["192.0.2.20"], "AAAA": ["2001:db8::20"]}
        assert len(evidence["by_resolver"]) == 3 and evidence["differences"]["A"]
        assert all(chain["terminal"] == "fixture.gccdn.net" and chain["status"] == "complete"
                   for chain in evidence["chains"].values())
        assert all("dnsx" in sources and "dig" in sources for sources in evidence["by_source"].values())
        assert evidence["by_resolver"][resolvers[1]]["MX"] == ["10 mail.example.invalid"]
        assert evidence["by_resolver"][resolvers[1]]["NS"] == ["ns1.example.invalid"]
        assert db.get_fact("cdn:app.example.invalid")
        assert selected_targets(ctx) == ["192.0.2.20", "2001:db8::20"]
        assert db.rows("SELECT domain FROM domains") == [{"domain": "app.example.invalid"}]
        assert not db.rows("SELECT * FROM dns_records WHERE value IN ('0.0.0.0', '198.18.0.8')")
        assert (ctx.stage_dir / "dns-observations.json").is_file()


def test_dig_loop_hop_limit_dangling_and_timeout(bridge, db, tmp_path, project):
    from asm.stages import s5_dns_cdn
    jobs = JobManager(bridge, db, tmp_path, poll_seconds=0.1)
    records = {"loop.example.invalid": {"CNAME": ["loop2.example.invalid"]},
        "loop2.example.invalid": {"CNAME": ["loop.example.invalid"]},
        "limit.example.invalid": {"CNAME": ["hop1.example.invalid"]},
        "hop1.example.invalid": {"CNAME": ["hop2.example.invalid"]},
        "hop2.example.invalid": {"CNAME": ["hop3.example.invalid"]},
        "exact.example.invalid": {"CNAME": ["end1.example.invalid"]},
        "end1.example.invalid": {"CNAME": ["end2.example.invalid"]}, "end2.example.invalid": {},
        "dangling.example.invalid": {"CNAME": ["missing.other.invalid"]},
        "timeout.example.invalid": {"DROP": True}}
    for domain in ("loop", "limit", "exact", "dangling", "timeout"):
        db.domain(Domain(domain + ".example.invalid"))
    with dns_servers(bridge, jobs, project, [records]) as resolvers:
        ctx = dns_context(bridge, db, jobs, tmp_path, project, resolvers, dnsx=False, max_cname_hops=2)
        result = s5_dns_cdn.run(ctx)
        assert result.status == "partial"
        for domain, state in (("loop", "loop"), ("limit", "max_hops"), ("exact", "complete"),
                              ("dangling", "nxdomain"), ("timeout", "error")):
            evidence = db.get_fact(f"dns:{domain}.example.invalid")
            assert evidence["chains"][resolvers[0]]["status"] == state
        assert db.rows("SELECT * FROM takeovers") == []  # NXDOMAIN alone is a candidate.
        assert db.rows("SELECT kind FROM findings WHERE kind='dangling_cname_candidate'")


def oneforall_context(bridge, db, tmp_path, project, monkeypatch, mode):
    from asm.utils.oneforall import PASSIVE_MODULES
    jobs = JobManager(bridge, db, tmp_path, poll_seconds=0.1)
    run = jobs.run

    def offline_run(tool, args, **kwargs):
        inputs = dict(kwargs.pop("inputs"))
        inputs["oneforall_probe.py"] = (project / "tests/fixtures/oneforall_probe.py").read_text(encoding="utf-8")
        inputs["fixture.json"] = json.dumps({"mode": mode})
        return run(tool, ["{job}/oneforall_probe.py", *args[1:]], inputs=inputs, **kwargs)
    monkeypatch.setattr(jobs, "run", offline_run)
    data = {"profile": "oneforall-test", "oneforall": {"modules": list(PASSIVE_MODULES),
        "module_timeout": 0.1 if mode == "module_timeout" else 5, "request_timeout": 1},
        "limits": {"oneforall_timeout": 3 if mode == "job_timeout" else 30}}
    scope = Scope({"targets": {"roots": ["ops.example.invalid", "lab.example.invalid"]},
        "scope": {"exclude_saas": ["blocked.ops.example.invalid", "blocked.lab.example.invalid"]}}, passive_only=True)
    return StageContext(Config(data, project / "profiles/test.yaml", project), db, bridge, jobs, scope,
                        tmp_path / "stage4", passive_only=True)


def test_oneforall_native_sources_scope_isolation_and_reuse(bridge, db, tmp_path, project, monkeypatch):
    from asm.stages import oneforall
    from asm.utils.oneforall import PASSIVE_MODULES
    ctx = oneforall_context(bridge, db, tmp_path, project, monkeypatch, "success")
    options = oneforall.settings(ctx.config)
    first = oneforall.submit(ctx, "ops.example.invalid", options)
    accepted, notes = oneforall.ingest(ctx, "ops.example.invalid", first)
    path = ctx.jobs.result_dir(first)
    assert not notes, (notes, (path / "job.log").read_text(encoding="utf-8"))
    assert first.rc == 0 and len(accepted) == 23
    evidence = db.get_fact("oneforall:ops.example.invalid")
    assert len(evidence["excluded"]) == 7 and evidence["run"]["root"] == "ops.example.invalid"
    assert set(evidence["run"]["modules"]) == set(PASSIVE_MODULES)
    assert all(state["status"] == "completed" for state in evidence["run"]["modules"].values())
    assert all(value is False for value in evidence["run"]["flags"].values())
    requests = [json.loads(line) for line in (path / "fixture-requests.jsonl").read_text().splitlines()]
    assert len(requests) == 8 and {row["host"] for row in requests} == set(PASSIVE_MODULES.values())
    assert all(row["verify"] is True and row["allow_redirects"] is False for row in requests)
    assert (path / "network-attempts.jsonl").read_text() == ""
    assert (path / "vendor-results/result.sqlite3").is_file()
    exported = json.loads((path / "oneforall.json").read_text(encoding="utf-8"))
    assert {row["subdomain"] for row in exported} == {
        "ops.example.invalid", "api.ops.example.invalid", "mail.ops.example.invalid",
        "blocked.ops.example.invalid", "dns-only.ops.example.invalid", "url-only.ops.example.invalid"}
    assert len(db.rows("SELECT sources FROM domains WHERE domain='api.ops.example.invalid'")[0]["sources"].split(",")) == 7
    assert not db.rows("SELECT * FROM assets") and not db.rows("SELECT * FROM dns_records")
    cached = oneforall.submit(ctx, "ops.example.invalid", options)
    assert cached.jobid == first.jobid and len(ctx.jobs.handles) == 1
    second = oneforall.submit(ctx, "lab.example.invalid", options)
    accepted, notes = oneforall.ingest(ctx, "lab.example.invalid", second)
    assert accepted and not notes and second.jobid != first.jobid
    second_export = json.loads((ctx.jobs.result_dir(second) / "oneforall.json").read_text(encoding="utf-8"))
    assert all(row["subdomain"] == "lab.example.invalid" or row["subdomain"].endswith(".lab.example.invalid")
               for row in second_export)


@pytest.mark.parametrize("mode", ["empty", "partial", "module_timeout", "job_timeout"])
def test_oneforall_native_empty_partial_and_timeouts(bridge, db, tmp_path, project, monkeypatch, mode):
    from asm.stages import oneforall
    ctx = oneforall_context(bridge, db, tmp_path, project, monkeypatch, mode)
    options = oneforall.settings(ctx.config)
    handle = oneforall.submit(ctx, "ops.example.invalid", options)
    accepted, notes = oneforall.ingest(ctx, "ops.example.invalid", handle)
    path = ctx.jobs.result_dir(handle)
    evidence = db.get_fact("oneforall:ops.example.invalid")
    assert (path / "network-attempts.jsonl").read_text() == ""
    if mode == "empty":
        assert not accepted and not notes and handle.rc == 0, (notes, (path / "job.log").read_text(encoding="utf-8"))
        assert evidence["status"] == "completed" and json.loads((path / "oneforall.json").read_text()) == []
    else:
        assert notes and evidence["status"] == "partial"
        assert db.rows("SELECT kind FROM findings WHERE kind='oneforall_partial'")
        assert handle.rc == (124 if mode == "job_timeout" else 2), (evidence, (path / "job.log").read_text(encoding="utf-8"))
        if mode != "job_timeout":
            assert accepted and evidence["run"]["status"] == "partial"
            state = evidence["run"]["modules"]["modules.certificates.certspotter"]
            assert state["status"] == ("partial" if mode == "partial" else "timed_out")
        retry = oneforall.submit(ctx, "ops.example.invalid", options)
        oneforall.ingest(ctx, "ops.example.invalid", retry)
        assert retry.jobid != handle.jobid  # A failed run is never cached as a completed collector.

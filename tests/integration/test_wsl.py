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

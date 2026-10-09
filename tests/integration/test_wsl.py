import os
import shutil
import sys

import pytest

from asm.bridge import Bridge, JobManager, WsFs

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

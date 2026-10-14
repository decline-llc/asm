import subprocess
import sys
import threading

import pytest

from asm.orchestrator import Workbench
from asm.run_lock import FileLease, LeaseBusy
from tests.unit.test_orchestrator import configuration, local_asset, workbench_root  # noqa: F401


def test_lease_blocks_other_process_then_releases(tmp_path):
    lock_path = tmp_path / "worker.lock"
    script = "from asm.run_lock import FileLease,LeaseBusy; import sys\ntry: FileLease(sys.argv[1]).close()\nexcept LeaseBusy: sys.exit(17)\n"
    with FileLease(lock_path):
        child = subprocess.run([sys.executable, "-c", script, str(lock_path)], capture_output=True)
        assert child.returncode == 17, child.stderr.decode()
    child = subprocess.run([sys.executable, "-c", script, str(lock_path)], capture_output=True)
    assert child.returncode == 0, child.stderr.decode()


def test_second_workbench_cannot_recover_or_resume_live_worker(workbench_root):  # noqa: F811
    entered, release = threading.Event(), threading.Event()
    calls = []

    def adapter(ctx):
        calls.append(ctx.target)
        entered.set()
        assert release.wait(5)
        return local_asset(ctx)

    first = Workbench(workbench_root, adapters={"web_visit": adapter})
    project = first.save_project(configuration(["http://localhost:8765/"]))
    run = first.start(project["project_id"])
    assert entered.wait(5)
    try:
        second = Workbench(workbench_root)
        assert second.run(run["run_id"])["status"] == "running"
        with pytest.raises(LeaseBusy):
            second.resume(run["run_id"], background=False)
        assert second.run(run["run_id"])["steps"][0]["status"] == "running"
    finally:
        release.set()
        first.threads[run["run_id"]].join(5)
    assert len(calls) == 1
    assert first.run(run["run_id"])["status"] == "completed"

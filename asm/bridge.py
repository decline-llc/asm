"""WSL control and file exchange. Tools never read or write /mnt or UNC paths."""
import hashlib
import json
import os
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .models import utcnow


class BridgeError(RuntimeError):
    pass


def decode(data):
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="replace").lstrip("\ufeff")
    return data.decode("utf-8", errors="replace")


def native_path(path):
    path = str(path)
    if not path.startswith("/") or "\\" in path or "\x00" in path:
        raise BridgeError("An absolute WSL POSIX path is required")
    if path == "/mnt" or path.startswith("/mnt/") or ".." in PurePosixPath(path).parts:
        raise BridgeError("WSL tools must use the native filesystem")
    return path


class Bridge:
    def __init__(self, distro=None, user=None, *, executable="wsl.exe", runner=None):
        self.distro = distro or os.getenv("WSL_DISTRO", "Ubuntu-22.04")
        self.user = user if user is not None else os.getenv("WSL_USER", "")
        self.executable = executable
        self.runner = runner or subprocess.run
        self._home = None

    def argv(self, script, *, root=False, cwd=None):
        args = [self.executable, "-d", self.distro]
        if root or self.user:
            args += ["-u", "root" if root else self.user]
        if cwd:
            args += ["--cd", native_path(cwd)]
        return args + ["--", "bash", "-lc", "export LC_ALL=C.UTF-8; " + script]

    def control(self, script, *, root=False, cwd=None, data=None, timeout=30, check=True):
        try:
            result = self.runner(self.argv(script, root=root, cwd=cwd), input=data,
                                 capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BridgeError(f"WSL unavailable: {exc}; check wsl --list --verbose") from exc
        if check and result.returncode:
            raise BridgeError(f"WSL rc={result.returncode}: {decode(result.stderr)[-1500:]}")
        return result

    @property
    def home(self):
        if self._home is None:
            self._home = native_path(decode(self.control('printf "%s" "$HOME"').stdout).strip())
        return self._home

    @property
    def workspace(self):
        return self.home + "/asm-ws"

    def command(self, tool, args=(), *, timeout=900):
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", tool) or tool.startswith("-"):
            raise BridgeError("Invalid tool name")
        if "/" in tool:
            native_path(tool)
        if timeout <= 0:
            raise BridgeError("Timeout must be positive")
        for arg in args:
            if str(arg).startswith(("/mnt/", "\\\\wsl", "C:\\", "D:\\")):
                raise BridgeError("Cross-boundary tool file paths are forbidden")
        path = shlex.quote(self.workspace + "/bin") + ":" + shlex.quote(self.workspace + "/tools/wafw00f/.venv/bin")
        return f"export PATH={path}:$PATH; timeout --signal=TERM --kill-after=5s {int(timeout)}s " + shlex.join(
            [tool] + [str(a) for a in args])


class WsFs:
    def __init__(self, bridge):
        self.bridge = bridge

    def mkdir(self, path):
        self.bridge.control("mkdir -p -- " + shlex.quote(native_path(path)))

    def write_bytes(self, path, data):
        self.bridge.control("cat > " + shlex.quote(native_path(path)), data=data)

    def read_text(self, path):
        return decode(self.bridge.control("cat -- " + shlex.quote(native_path(path))).stdout)

    def exists(self, path):
        return self.bridge.control("test -e " + shlex.quote(native_path(path)), check=False).returncode == 0

    @staticmethod
    def extract_archive(stream, destination, *, byte_limit=2_000_000_000):
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        total = 0
        with tarfile.open(fileobj=stream, mode="r|*") as archive:
            for member in archive:
                name = member.name
                parts = PurePosixPath(name).parts
                if (member.issym() or member.islnk() or not (member.isdir() or member.isfile())
                        or PurePosixPath(name).is_absolute() or ".." in parts or "\\" in name or ":" in name):
                    raise BridgeError(f"Unsafe archive member: {name}")
                target = (destination / Path(*parts)).resolve()
                if not target.is_relative_to(destination):
                    raise BridgeError("Archive escapes destination")
                total += member.size
                if total > byte_limit:
                    raise BridgeError("Archive exceeds byte limit")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as src, target.open("wb") as dst:
                        while chunk := src.read(1 << 20):
                            dst.write(chunk)

    def pull_dir(self, path, destination):
        command = "tar cf - -C " + shlex.quote(native_path(path)) + " ."
        # Spool on disk: binary results are never decoded into text or buffered in RAM.
        with tempfile.TemporaryFile() as stream:
            result = self.bridge.runner(self.bridge.argv(command), stdout=stream,
                                        stderr=subprocess.PIPE, timeout=300)
            if result.returncode:
                raise BridgeError(decode(result.stderr))
            stream.seek(0)
            self.extract_archive(stream, destination)


@dataclass
class JobHandle:
    jobid: str
    directory: str
    tool: str
    stage: str
    status: str = "running"
    rc: int | None = None


class JobManager:
    def __init__(self, bridge, db, output, *, foreground_seconds=60, poll_seconds=5):
        self.bridge, self.db, self.output = bridge, db, Path(output)
        self.fs = WsFs(bridge)
        self.foreground_seconds, self.poll_seconds = foreground_seconds, poll_seconds
        self.handles = []
        self.processes = {}

    def run(self, tool, args=(), *, stage, timeout=900, background=False, root=False,
            inputs=None, idempotent=False):
        inputs = inputs or {}
        fingerprint = hashlib.sha256(json.dumps([tool, list(args), inputs, root, self.bridge.distro,
                                                self.bridge.user], sort_keys=True).encode()).hexdigest()
        previous = self.db.rows("SELECT * FROM jobs WHERE fingerprint=? AND status='completed' "
                                "ORDER BY finished DESC LIMIT 1", (fingerprint,))
        if idempotent and previous and Path(previous[0]["result_dir"]).is_dir():
            item = previous[0]
            return JobHandle(item["jobid"], self.bridge.workspace + "/results/" + item["jobid"],
                             tool, stage, "completed", 0)
        jobid = uuid.uuid4().hex
        directory = self.bridge.workspace + "/results/" + jobid
        self.fs.mkdir(directory)
        for name, content in inputs.items():
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                raise BridgeError("Invalid input filename")
            self.fs.write_bytes(directory + "/" + name, content.encode() if isinstance(content, str) else content)
        cmd = self.bridge.command(tool, [str(a).replace("{job}", directory) for a in args], timeout=timeout)
        # Every exit code, including timeout and failure, gets an atomic completion marker.
        script = ("#!/usr/bin/env bash\nset +e\ncd -- " + shlex.quote(directory) + "\n"
                  "echo $$ > pid\n" + cmd + "\nrc=$?\n"
                  "printf '%s\\n' \"$rc\" > rc.tmp\nmv rc.tmp rc\ntouch done\nexit \"$rc\"\n")
        self.fs.write_bytes(directory + "/runner.sh", script.encode())
        # Keep the Windows WSL client alive asynchronously. On some WSL/systemd builds,
        # orphaned Linux processes get reaped when the last WSL client disconnects.
        # Popen preserves the session without blocking orchestration at 60 seconds.
        launcher = ("cd -- " + shlex.quote(directory) + "; nohup bash runner.sh > job.log 2>&1 < /dev/null")
        result_dir = str(self.output / "results" / stage / jobid)
        self.db.upsert("jobs", {"jobid": jobid, "stage": stage, "tool": tool, "cmd": cmd,
                               "status": "running", "started": utcnow(), "finished": "", "rc": None,
                               "log_path": str(Path(result_dir) / "job.log"), "result_dir": result_dir,
                               "fingerprint": fingerprint}, ("jobid",))
        handle = JobHandle(jobid, directory, tool, stage)
        self.handles.append(handle)
        try:
            self.processes[jobid] = subprocess.Popen(self.bridge.argv(launcher, root=root, cwd=directory),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.db.upsert("jobs", {"jobid": jobid, "status": "failed", "finished": utcnow()}, ("jobid",))
            handle.status = "failed"
            raise
        self.log(handle, event="submitted")
        if not background:
            self.wait(handle, max_seconds=self.foreground_seconds)
        return handle

    def log(self, handle, **extra):
        path = self.output / "logs" / "bridge.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = self.db.rows("SELECT cmd,started FROM jobs WHERE jobid=?", (handle.jobid,))[0]
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"ts": utcnow(), "jobid": handle.jobid, "stage": handle.stage,
                                     "tool": handle.tool, "cmd": row["cmd"], "rc": handle.rc,
                                     **extra}, ensure_ascii=False) + "\n")

    def poll(self, handle):
        if handle.status != "running":
            return True
        if not self.fs.exists(handle.directory + "/done"):
            process = self.processes.get(handle.jobid)
            if process is not None and process.poll() is not None:
                handle.rc = process.returncode or -1
                handle.status = "failed"
                self.db.upsert("jobs", {"jobid": handle.jobid, "status": "failed", "rc": handle.rc,
                                       "finished": utcnow()}, ("jobid",))
                self.log(handle, event="client_exited_without_done")
                return True
            return False
        handle.rc = int(self.fs.read_text(handle.directory + "/rc").strip())
        result_dir = self.output / "results" / handle.stage / handle.jobid
        self.fs.pull_dir(handle.directory, result_dir)
        handle.status = "completed" if handle.rc == 0 else "failed"
        self.db.upsert("jobs", {"jobid": handle.jobid, "status": handle.status,
                               "rc": handle.rc, "finished": utcnow()}, ("jobid",))
        self.log(handle, event="finished", bytes=sum(p.stat().st_size for p in result_dir.rglob("*") if p.is_file()))
        process = self.processes.pop(handle.jobid, None)
        if process is not None:
            process.wait(timeout=5)
        return True

    def wait(self, handle, *, max_seconds=None):
        started = time.monotonic()
        while not self.poll(handle):
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                self.log(handle, event="background_after_timeout")
                return handle
            time.sleep(self.poll_seconds)
        return handle

    def wait_all(self, *, max_seconds=None):
        started = time.monotonic()
        while any(h.status == "running" for h in self.handles):
            for handle in self.handles:
                self.poll(handle)
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                break
            if any(h.status == "running" for h in self.handles):
                time.sleep(self.poll_seconds)
        return self.handles

    def recover(self):
        for row in self.db.rows("SELECT * FROM jobs WHERE status='running'"):
            self.handles.append(JobHandle(row["jobid"], self.bridge.workspace + "/results/" + row["jobid"],
                                          row["tool"], row["stage"]))
        return self.handles

    def result_dir(self, handle):
        return Path(self.db.rows("SELECT result_dir FROM jobs WHERE jobid=?", (handle.jobid,))[0]["result_dir"])

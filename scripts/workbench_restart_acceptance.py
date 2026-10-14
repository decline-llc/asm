"""Real backend process death/restart on an isolated, owned loopback fixture."""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(root, number):
    import asm.conf
    import dotenv
    from asm.api import create_server
    root = Path(root)

    def denied(kind):
        with (root / "forbidden-access.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind}) + "\n")
        raise RuntimeError("Acceptance forbids " + kind)

    asm.conf.load_dotenv = lambda *_a, **_k: denied("dotenv")
    dotenv.load_dotenv = lambda *_a, **_k: denied("dotenv")
    dotenv.dotenv_values = lambda *_a, **_k: denied("settings")
    original_address = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def local_address(host, *args, **kwargs):
        if host not in {"localhost", "127.0.0.1", "::1"}:
            denied("external_dns")
        return original_address(host, *args, **kwargs)

    def local_connect(connection, address):
        if address[0] not in {"127.0.0.1", "::1"}:
            denied("external_connection")
        return original_connect(connection, address)

    def local_connect_ex(connection, address):
        if address[0] not in {"127.0.0.1", "::1"}:
            denied("external_connection")
        return original_connect_ex(connection, address)

    socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = local_address, local_connect, local_connect_ex
    server = create_server(root, port=0)
    (root / f"ready-{number}.json").write_text(json.dumps({"pid": __import__("os").getpid(), "port": server.server_address[1]}))
    server.serve_forever()


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        with self.server.lock:
            self.server.requests.append(self.path)
        if self.path.endswith("/hold"):
            self.server.release.wait(45)
        raw = ("<html><title>Restart fixture " + self.path + "</title></html>").encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *_):
        pass


def hashes(directory):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for part in ("exports", "evidence")
            for path in (directory / part).rglob("*") if path.is_file()}


def ledger(root):
    from asm.db import Database
    with Database(root / "data/account-rate-ledger.sqlite") as db:
        return {"usage": db.rows("SELECT * FROM sources"), "last_request": db.rows("SELECT * FROM rate_state")}


def main():
    from asm.db import Database
    from asm.panel.base import RateLimiter
    from asm.orchestrator import Workbench
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    output = ROOT / "data/validation/workbench-20261011" / ("restart-" + stamp)
    root = output / "workspace"
    (root / "profiles").mkdir(parents=True)
    shutil.copy2(ROOT / "profiles/modes.yaml", root / "profiles/modes.yaml")
    # This fake account consumes only its isolated test ledger; no provider call.
    with Database(root / "data/account-rate-ledger.sqlite") as db:
        limiter = RateLimiter(db, "fixture_account", daily=1)
        limiter.acquire()
    original_ledger = ledger(root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    server.daemon_threads = True
    server.requests, server.lock, server.release = [], threading.Lock(), threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fixture_url = "http://127.0.0.1:" + str(server.server_address[1])
    processes, logs, workers, checks, runs = [], [], [], {}, []

    def check(name, value):
        checks[name] = bool(value)
        print(("PASS " if value else "FAIL ") + name, flush=True)
        if not value:
            raise AssertionError(name)

    def launch():
        number = len(processes) + 1
        stream = (output / f"backend-{number}.log").open("wb")
        logs.append(stream)
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(root), "--number", str(number)],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        processes.append(process)
        ready = root / f"ready-{number}.json"
        deadline = time.monotonic() + 20
        while not ready.is_file() and time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Backend failed; inspect backend log")
            time.sleep(0.1)
        metadata = json.loads(ready.read_text())
        # Windows venv python.exe is a launcher; the ready file records the
        # actual interpreter PID, which is the process that owns the server.
        metadata["launcher_pid"] = process.pid
        workers.append(metadata)
        return httpx.Client(base_url="http://127.0.0.1:" + str(metadata["port"]), trust_env=False, timeout=10)

    def kill_worker(index):
        try:
            os.kill(workers[index]["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            if processes[index].poll() is None:
                raise
        processes[index].wait(timeout=10)

    def request(client, method, path, payload=None):
        assert path.startswith(("/api/projects", "/api/runs/")) and "settings" not in path
        response = client.request(method, path, json=payload)
        response.raise_for_status()
        return response.json()

    def wait(client, run_id, predicate):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            run = request(client, "GET", f"/api/runs/{run_id}/state")
            if predicate(run):
                return run
            time.sleep(0.1)
        raise AssertionError("State deadline expired")

    def config(name):
        urls = [fixture_url + "/" + name + suffix for suffix in ("/first", "/hold", "/last")]
        return {"schema_version": 2, "profile": name, "mode_preset": "authorized_verify", "authorization": True,
            "authorization_details": {"authority": "fixture_owner", "reference": "owned_loopback_restart_fixture", "environment": "local_lab"},
            "execution": {"source": "live", "target_local": True}, "targets": {"roots": []},
            "scope_sets": {key: {"include": ["127.0.0.1/32"], "exclude": []} for key in ("investigation", "verification", "extended")},
            "permissions": {"web_visit": {"allow": True, "scope_ref": "verification"}},
            "plan": {"selection": "custom", "selected_capabilities": ["web_visit"], "selected_tools": ["target_http"],
                "params": {"web_visit": {"urls": urls, "timeout_seconds": 35, "requests_per_second": 1000}}},
            "budgets": {"max_rounds": 1, "max_hosts": 1, "max_duration_seconds": 120}}

    client = None
    error = None
    try:
        client = launch()
        for name, revoke in (("resume_fixture", False), ("revoke_fixture", True)):
            server.release.clear()
            value = config(name)
            request(client, "POST", "/api/projects", value)
            run = request(client, "POST", f"/api/projects/{name}/start", {})
            run_id = run["run_id"]
            run = wait(client, run_id, lambda r: r["steps"][0]["status"] == "completed" and "/" + name + "/hold" in server.requests)
            request(client, "POST", f"/api/runs/{run_id}/export", {})
            directory = Path(run["directory"])
            prior = hashes(directory)
            checkpoint = directory / "checkpoints/current.json"
            check(name + " persisted running checkpoint", json.loads(checkpoint.read_text())["run_id"] == run_id)
            completed_step = run["steps"][0]["id"]
            kill_worker(-1)
            client.close()
            if revoke:
                value["permissions"]["web_visit"]["allow"] = False
                Workbench(root, recover=False).save_project(value, project_id=name)
            server.release.set()
            client = launch()
            recovered = request(client, "GET", f"/api/runs/{run_id}/state")
            check(name + " restart identifies original interrupted run", recovered["run_id"] == run_id and recovered["status"] == "interrupted" and recovered["steps"][0]["status"] == "completed")
            check(name + " interrupted dual delivery", recovered["snapshot"]["run_status"] == "interrupted" and recovered["snapshot"]["status"] == "complete")
            request(client, "POST", f"/api/runs/{run_id}/resume", {})
            final = wait(client, run_id, lambda r: r["status"] in {"completed", "partial"} and r.get("snapshot", {}).get("run_status") == r["status"])
            check(name + " completed request is not repeated", server.requests.count("/" + name + "/first") == 1 and final["steps"][0]["id"] == completed_step and final["steps"][0]["attempt"] == 1)
            check(name + " prior evidence and exports remain immutable", all(Path(path).is_file() and hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in prior.items()))
            check(name + " assets deduplicate", len(final["assets"]) == 1)
            wb = Workbench(root, recover=False)
            events = wb.store.events(run_id)
            first_events = [e for e in events if e["kind"] == "tool_call" and e["data"].get("params", {}).get("url", "").endswith("/first")]
            check(name + " no completed call event duplicated", len(first_events) == 1 and len({e["id"] for e in events}) == len(events))
            if revoke:
                check("Revocation survives recovery", all(s["status"] == "skipped" and "function_permission_denied" in s["reason"] for s in final["steps"][1:]) and
                      server.requests.count("/" + name + "/hold") == 1 and "/" + name + "/last" not in server.requests)
            else:
                check("Unfinished requests resume with original queue", all(s["status"] == "completed" for s in final["steps"]) and server.requests.count("/" + name + "/last") == 1)
            runs.append({"run_id": run_id, "directory": str(directory), "checkpoint": str(checkpoint), "config": final["config"],
                         "status": final["status"], "snapshot": final["snapshot"], "steps": final["steps"]})
        check("Account ledger is not reset", ledger(root) == original_ledger)
        check("No credentials or external access attempted", not (root / "forbidden-access.jsonl").exists())
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
        checks["Harness completed all steps"] = False
        print(error, flush=True)
    finally:
        if client:
            client.close()
        server.release.set()
        for index, process in enumerate(processes):
            if process.poll() is None:
                if index < len(workers):
                    kill_worker(index)
                else:
                    process.kill()
                    process.wait(timeout=10)
        for stream in logs:
            stream.close()
        server.shutdown()
        server.server_close()
        summary = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": checks, "error": error, "workers": workers,
            "runs": runs, "workspace": str(root), "database": str(root / "data/workbench.sqlite"),
            "ledger": str(root / "data/account-rate-ledger.sqlite"), "ledger_before": original_ledger, "ledger_after": ledger(root),
            "fixture_url": fixture_url, "requests": server.requests, "processes_closed": all(p.poll() is not None for p in processes)}
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Evidence: " + str(output / "summary.json"), flush=True)
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--number", type=int, default=1)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.number)
    else:
        raise SystemExit(main())

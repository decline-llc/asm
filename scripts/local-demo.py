"""Reproducible CLI demo; starts only localhost fixtures, stops them on exit."""
import json
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from asm.bridge import Bridge, WsFs
import runpy

fixture = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests/fixtures/server.py"))
start_server, tcp_listener, udp_listener = (fixture[n] for n in ("start_server", "tcp_listener", "udp_listener"))


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    bridge = Bridge()
    fs = WsFs(bridge)
    directory = bridge.workspace + "/tmp/local-harness"
    fs.mkdir(directory)
    fs.write_bytes(directory + "/server.py", (root / "tests/fixtures/server.py").read_bytes())
    fs.write_bytes(directory + "/run.sh", (f"#!/bin/bash\ncd '{directory}'\n"
        "exec timeout 180 python3 server.py --extra-listeners\n").encode())
    wsl = subprocess.Popen(bridge.argv(f"bash {directory}/run.sh"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    http = start_server(8765)
    listeners = [tcp_listener(8766), tcp_listener(8768), udp_listener(8767)]
    try:
        time.sleep(1)
        command = [sys.executable, "-m", "asm", "run", "--profile", "test", "--stages", "1,3,5,6,7,8", "--target-local"]
        result = subprocess.run(command, cwd=root)
        if result.returncode:
            raise SystemExit(result.returncode)
        from asm.db import Database
        with Database(root / "data/test/asm.db") as db:
            summary = {"assets": db.rows("SELECT COUNT(*) n FROM assets")[0]["n"],
                       "urls": db.rows("SELECT COUNT(*) n FROM urls")[0]["n"],
                       "ports": db.rows("SELECT port,proto FROM assets ORDER BY port,proto"),
                       "quarantine": db.rows("SELECT COUNT(*) n FROM assets_quarantine")[0]["n"]}
            (root / "data/validation").mkdir(parents=True, exist_ok=True)
            (root / "data/validation/local-demo.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        http.shutdown()
        http.server_close()
        for sock in listeners:
            sock.close()
        # This process was created here; stop only its bounded WSL client/fixture.
        wsl.terminate()
        wsl.wait(timeout=10)


if __name__ == "__main__":
    main()

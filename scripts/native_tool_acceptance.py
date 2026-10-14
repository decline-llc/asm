"""Exercise installed DNS/port tools against fixtures inside the original WSL."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from asm.bridge import Bridge, WsFs
from asm.orchestrator import Workbench


FIXTURE = '''import json, sys
from dns_server import DNSFixture
from server import start_server
http = start_server(0)
dns = DNSFixture({"localhost": {"A": ["127.0.0.1", "198.18.0.2"]}})
print(json.dumps({"http_port": http.server_port, "dns_port": dns.port}), flush=True)
try:
    sys.stdin.buffer.read(1)
finally:
    dns.close()
    http.shutdown()
    http.server_close()
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distro", default=os.getenv("WSL_DISTRO", "Ubuntu"))
    args = parser.parse_args()
    os.environ["WSL_DISTRO"] = args.distro
    repository = Path(__file__).resolve().parents[1]
    root = repository / "data/validation" / ("native-tools-live-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    (root / "profiles").mkdir(parents=True)
    shutil.copy(repository / "profiles/modes.yaml", root / "profiles/modes.yaml")
    bridge = Bridge(args.distro)
    fs = WsFs(bridge)
    directory = bridge.workspace + "/results/acceptance-" + uuid.uuid4().hex
    fs.mkdir(directory)
    for name, content in {"server.py": (repository / "tests/fixtures/server.py").read_bytes(),
                          "dns_server.py": (repository / "tests/fixtures/dns_server.py").read_bytes(),
                          "fixture.py": FIXTURE.encode()}.items():
        fs.write_bytes(directory + "/" + name, content)
    results = []
    process = subprocess.Popen(bridge.argv("exec python3 fixture.py", cwd=directory),
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ready = json.loads(process.stdout.readline())
        wb = Workbench(root)
        for tool, capability in [("dig_probe", "dns_recursive"), ("dnsx", "dns_recursive"),
                                 ("naabu", "tcp_scan"), ("a_scan", "tcp_scan"), ("nmap", "tcp_scan")]:
            params = {"ports": str(ready["http_port"]), "timeout_seconds": 3, "host_timeout_seconds": 40,
                      "packets_per_second": 10, "record_types": ["A"], "resolvers": ["127.0.0.1:" + str(ready["dns_port"])],
                      "reject_fake_ip": True, "requests_per_second": 2}
            config = {"schema_version": 2, "profile": "local-" + tool, "mode_preset": "full_asm", "authorization": True,
                "execution": {"source": "live", "target_local": True}, "targets": {"roots": ["localhost"]},
                "ports": {"targets": ["127.0.0.1"]},
                "scope_sets": {scope: {"include": ["localhost", "127.0.0.1/32"]} for scope in ("investigation", "verification", "extended")},
                "permissions": {capability: {"allow": True, "scope_ref": "verification"}},
                "plan": {"selection": "custom", "selected_capabilities": [capability], "selected_tools": [tool], "params": {capability: params}},
                "budgets": {"max_rounds": 1, "max_duration_seconds": 90}}
            item = wb.save_project(config)
            run = wb.start(item["project_id"], background=False)
            observed = any(a.get("ip") == "127.0.0.1" and (capability == "dns_recursive" or a.get("port") == ready["http_port"]) for a in run["assets"])
            status = {"tool": tool, "run_id": run["run_id"], "status": run["status"], "observed_fixture": observed,
                      "steps": [{"status": s["status"], "reason": s["reason"]} for s in run["steps"]], "directory": run["directory"]}
            results.append(status)
            (root / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(status), flush=True)
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
    return 0 if all(r["status"] == "completed" and r["observed_fixture"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

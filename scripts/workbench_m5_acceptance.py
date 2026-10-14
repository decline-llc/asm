"""Persist real loopback M5 runs, evidence, and both report variants. No secrets."""
import json
import socket
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from asm.orchestrator import Workbench
from asm.run_store import atomic_json


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append({"path": self.path, "origin": self.headers.get("Origin", "")})
        routes = {
            "/": (200, '<title>M5 local fixture</title><a href="/child#one">child</a>'
                '<a href="/child#two">same child</a><a href="http://192.0.2.29/foreign">foreign</a>'
                '<script src="/app.js"></script><script src="http://192.0.2.29/foreign.js"></script>'),
            "/child": (200, '<a href="/#back">home</a><a href="/grand">grand</a>'),
            "/grand": (200, "M5 grandchild"),
            "/app.js": (200, 'const local="/api/local";const foreign="http://192.0.2.29/api/foreign";' + "X" * 300),
            "/takeover": (404, "There isn't a GitHub Pages site here"),
            "/private": (401, "Fixture denial"), "/open": (200, "Fixture anonymous response"),
        }
        code, body = routes.get(self.path, (404, "M5 fixture not found"))
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.headers.get("Origin"):
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


def main():
    root = Path(__file__).resolve().parents[1]
    tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    server.requests = []
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = "http://localhost:" + str(server.server_address[1])
    checks = [
        ("web_crawl", "native_crawler", "/", {"max_depth": 2, "max_urls_per_host": 10}),
        ("js_analysis", "native_js_analyzer", "/", {"max_files_per_host": 1, "max_bytes_per_file": 96}),
        ("vulnerability_check", "native_risk_checks", "/", {"approved_checks": ["security_headers", "cors_policy"]}),
        ("takeover_probe", "stage_5_takeover_fingerprint", "/takeover", {"approved_providers": ["GitHub Pages"]}),
        ("auth_audit", "native_auth_audit", "/", {"approved_checks": ["anonymous_protected_paths"],
            "protected_paths": ["/private", "/open", "/missing"]}),
    ]
    original_resolver = socket.getaddrinfo
    def local_only(host, *args, **kwargs):
        if host not in {"localhost", "127.0.0.1", "::1"}:
            summary["external_resolution_attempts"] += 1
            raise AssertionError("Unexpected non-local resolution")
        return original_resolver(host, *args, **kwargs)
    summary = {"fixture": base, "runs": [], "secret_reads": 0, "external_resolution_attempts": 0}
    def forbid_secret(*_args, **_kwargs):
        summary["secret_reads"] += 1
        raise AssertionError("Unexpected secret read")
    try:
        with patch("asm.conf.load_dotenv", side_effect=forbid_secret), \
                patch("dotenv.load_dotenv", side_effect=forbid_secret), \
                patch("socket.getaddrinfo", side_effect=local_only):
            wb = Workbench(root, recover=False, validation=True)
            for capability, tool, path, params in checks:
                project_id = "m5_" + capability + "_" + tag
                config = {"schema_version": 2, "profile": project_id, "mode_preset": "full_asm", "authorization": True,
                    "execution": {"source": "live", "target_local": True}, "targets": {"roots": ["localhost"]},
                    "scope_sets": {key: {"include": ["localhost", "127.0.0.1/32"], "exclude": []}
                        for key in ("investigation", "verification", "extended")},
                    "permissions": {capability: {"allow": True, "scope_ref": "extended"}},
                    "plan": {"selection": "custom", "selected_capabilities": [capability], "selected_tools": [tool],
                        "params": {capability: {"requests_per_second": 1000, "timeout_seconds": 2, **params}}},
                    "web": {"urls": [base + path]}, "budgets": {"max_rounds": 1, "max_hosts": 5, "max_duration_seconds": 60}}
                project = wb.save_project(config)
                before = len(server.requests)
                run = wb.start(project["project_id"], background=False)
                assert run["status"] == "completed" and run["snapshot"]["status"] == "complete", run["steps"]
                records = [json.loads(row["data"]) for row in wb.store.rows("SELECT data FROM records WHERE run=?", (run["run_id"],))]
                calls = server.requests[before:]
                assert not any(row["path"].startswith("/api/") for row in calls)
                summary["runs"].append({"capability": capability, "project_id": project_id, "run_id": run["run_id"],
                    "directory": run["directory"], "snapshot": run["snapshot"], "status": run["status"],
                    "local_requests": calls, "evidence_count": sum(row["category"] == "evidence_index" for row in records),
                    "findings": [row for row in records if row["category"] == "findings"],
                    "outside_leads": [row for row in records if row["category"] == "out_of_scope_leads"]})
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        summary["fixture_closed"] = True
        summary_path = root / "data" / "validation" / "workbench-20261011" / ("m5-native-" + tag + ".json")
        atomic_json(summary_path, summary)
    print(json.dumps({"summary": str(summary_path), "run_ids": [run["run_id"] for run in summary["runs"]],
        "statuses": [run["status"] for run in summary["runs"]], "fixture_closed": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()

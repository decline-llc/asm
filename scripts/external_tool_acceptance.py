"""Real HTTP scanner acceptance against the owned loopback fixture only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
from datetime import datetime

from asm.orchestrator import Workbench


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distro", default=os.getenv("WSL_DISTRO", "Ubuntu"))
    parser.add_argument("--tools", nargs="+", choices=["httpx", "ffuf", "katana", "gowitness", "wafw00f", "nuclei"])
    parser.add_argument("--screenshot-driver", choices=["chromedp", "gorod"], default="gorod")
    args = parser.parse_args()
    os.environ["WSL_DISTRO"] = args.distro
    repository = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("asm_local_http_fixture", repository / "tests/fixtures/server.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    root = repository / "data/validation" / ("external-tools-live-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    (root / "profiles").mkdir(parents=True)
    (root / "templates").mkdir()
    shutil.copy(repository / "profiles/modes.yaml", root / "profiles/modes.yaml")
    shutil.copy(repository / "tests/fixtures/nuclei-local-observation.yaml", root / "templates/local.yaml")
    server = fixture.start_server(0)
    base = "http://127.0.0.1:" + str(server.server_port)
    wb = Workbench(root)
    results = []
    try:
        for tool, capability in [("httpx", "web_visit"), ("ffuf", "web_path_enum"), ("katana", "web_crawl"), ("gowitness", "screenshot"), ("wafw00f", "vulnerability_check"), ("nuclei", "vulnerability_check")]:
            if args.tools and tool not in args.tools:
                continue
            config = {"schema_version": 2, "profile": "local-" + tool, "mode_preset": "full_asm", "authorization": True,
                "execution": {"source": "live", "target_local": True}, "targets": {"roots": ["localhost"]},
                "scope_sets": {scope: {"include": ["localhost", "127.0.0.1/32"]} for scope in ("investigation", "verification", "extended")},
                "permissions": {capability: {"allow": True, "scope_ref": "verification"}},
                "plan": {"selection": "custom", "selected_capabilities": [capability], "selected_tools": [tool],
                    "params": {capability: {"urls": [base + "/"], "max_requests_per_host": 40, "requests_per_second": 10,
                        "host_timeout_seconds": 120, "max_depth": 1, "max_urls_per_host": 10, "timeout_seconds": 45 if tool == "gowitness" else 10,
                        "driver": args.screenshot_driver, "approved_checks": ["waf_fingerprint"], "approved_templates": ["templates/local.yaml"]}}},
                "budgets": {"max_rounds": 1, "max_duration_seconds": 180}}
            item = wb.save_project(config)
            run = wb.start(item["project_id"], background=False)
            status = {"tool": tool, "run_id": run["run_id"], "status": run["status"], "steps": [{"status": s["status"], "reason": s["reason"]} for s in run["steps"]], "assets": len(run["assets"]), "directory": run["directory"]}
            results.append(status)
            (root / "summary.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(status, ensure_ascii=True), flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0 if all(r["status"] == "completed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

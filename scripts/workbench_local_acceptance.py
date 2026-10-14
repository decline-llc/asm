"""Run the real configured local adapters and preserve a new dual-report delivery."""
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from asm.orchestrator import Workbench  # noqa: E402
from tests.fixtures.server import start_server, tcp_listener, udp_listener  # noqa: E402


def main():
    http = start_server()
    tcp = tcp_listener(0)
    udp = udp_listener(0)
    url = f"http://127.0.0.1:{http.server_address[1]}"
    tcp_port, udp_port = tcp.getsockname()[1], udp.getsockname()[1]
    selected = ["tcp_scan", "udp_scan", "web_visit", "web_path_enum", "exposure_check", "screenshot"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    project_id = "lab_native_" + stamp
    config = {"schema_version": 2, "profile": project_id, "mode_preset": "full_asm", "authorization": True,
        "authorization_details": {"authority": "fixture_owner", "reference": "self_owned_local_fixture", "environment": "local_lab"},
        "execution": {"source": "live", "target_local": True},
        "targets": {"roots": [], "ip_cidrs": ["127.0.0.1/32"]},
        "scope_sets": {name: {"include": ["127.0.0.1/32"], "exclude": []} for name in ("investigation", "verification", "extended")},
        "permissions": {cap: {"allow": True, "scope_ref": "extended" if cap in {"udp_scan", "web_path_enum", "exposure_check"} else "verification"} for cap in selected},
        "plan": {"selection": "custom", "selected_capabilities": selected,
            "selected_tools": ["python_socket", "target_http", "stage_7_paths", "stage_7_exposure", "playwright"],
            "params": {"tcp_scan": {"engine": "python_socket", "ports": f"{http.server_address[1]},{tcp_port}"},
                "udp_scan": {"engine": "python_socket", "ports": str(udp_port)},
                "web_visit": {"urls": [url], "timeout_seconds": 3, "requests_per_second": 20},
                "web_path_enum": {"requests_per_second": 20, "max_requests_per_host": 20},
                "exposure_check": {"approved_checks": ["source_control_metadata", "public_api_schema"], "requests_per_second": 20},
                "screenshot": {"timeout_seconds": 5, "full_page": True}}},
        "ports": {"targets": ["127.0.0.1"], "engine": "python_socket"},
        "web": {"urls": [url]}, "budgets": {"max_rounds": 1, "max_hosts": 1, "max_duration_seconds": 120}}
    try:
        wb = Workbench(ROOT, validation=True)
        project = wb.save_project(config)
        run = wb.start(project["project_id"], background=False)
        pngs = list(Path(run["directory"]).glob("evidence/**/*.png"))
        summary = {"project_id": project_id, "run_id": run["run_id"], "status": run["status"],
            "directory": run["directory"], "snapshot_id": run["snapshot"]["snapshot_id"], "delivery": run["snapshot"]["status"],
            "steps": [{"capability": s["capability"], "tool": s["tool"], "status": s["status"], "reason": s["reason"]} for s in run["steps"]],
            "asset_count": len(run["assets"]), "png_count": len(pngs), "http_requests": http.requests,
            "fixture": {"http_url": url, "tcp": tcp_port, "udp": udp_port}, "credentials_loaded": False,
            "account_ledger": str(ROOT / "data/account-rate-ledger.sqlite"), "fixture_closed_after_run": True}
        directory = ROOT / "data/validation/workbench-20261011"
        path = directory / ("local-acceptance-" + stamp + ".json")
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if run["status"] == "completed" and run["snapshot"]["status"] == "complete" and pngs else 1
    finally:
        http.shutdown()
        http.server_close()
        tcp.close()
        udp.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Failing assertions for N1–N8 against the local built demo; blocks external traffic."""
import http.server
import json
import os
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/qa/frontend-n1-n8"
OUT.mkdir(parents=True, exist_ok=True)
os.environ["ASM_PROBE_OUT"] = str(OUT)
from review2_probes import CONTRAST_JS, VIEWS  # noqa: E402


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "frontend/dist"), **kwargs)

    def log_message(self, *args):
        pass


def main():
    checks, evidence, errors, external = {}, {}, [], []

    def check(name, condition):
        checks[name] = bool(condition)
        print(("PASS " if condition else "FAIL ") + name, flush=True)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/?demo=1"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")

            def route(request_route):
                parsed = urlsplit(request_route.request.url)
                if parsed.scheme in {"data", "blob"} or parsed.hostname == "127.0.0.1":
                    request_route.continue_()
                else:
                    external.append(request_route.request.url)
                    request_route.abort()

            context.route("**/*", route)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="networkidle")
            contrast = {}
            for view, label in VIEWS:
                page.locator(".sidebar .nav-item", has_text=label).click()
                contrast[view] = page.evaluate(CONTRAST_JS)
                check("N1 AA contrast " + view, contrast[view]["failing"] == 0)
            evidence["contrast"] = contrast
            layouts = {}
            for width, height in ((390, 844), (1280, 800), (1920, 1080)):
                page.set_viewport_size({"width": width, "height": height})
                for view, label in VIEWS:
                    page.locator(".sidebar .nav-item", has_text=label).click()
                    layout = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})")
                    layouts[f"{width}:{view}"] = layout
                    check(f"N2 {width}px {view} no document overflow", layout["scroll"] <= layout["client"])
                if width == 390:
                    page.locator(".sidebar .nav-item", has_text="项目概览").click()
                    page.screenshot(path=str(OUT / "390-overview.png"), full_page=True)
            evidence["layouts"] = layouts
            page.set_viewport_size({"width": 1440, "height": 900})
            page.locator(".sidebar .nav-item", has_text="调查任务").click()
            page.locator(".grid.cols-3 .lead-item", has_text="RUN-20261009-01").click()
            nodes = page.locator(".pipeline .step .node").all_inner_texts()
            evidence["stage_nodes"] = nodes
            check("N3 initial report stage is pending", len(nodes) == 8 and not nodes[-1].strip().startswith("●"))
            for label in ("项目概览", "报告中心"):
                page.locator(".sidebar .nav-item", has_text=label).click()
                text = page.locator("main").inner_text()
                check("N4 removed trusted asset disclosed in " + label, "离开可信集" in text and "oa.example.com" in text)
            page.locator(".sidebar .nav-item", has_text="资产探索").click()
            page.get_by_role("searchbox", name="搜索资产").fill("mail.example.com")
            page.locator("table.data tbody tr").first.click()
            page.locator(".drawer .tabs button", has_text="证据").click()
            log = page.locator(".drawer .log-box").inner_text()
            evidence["mail_raw_log"] = log
            check("N6 mail service raw record has no httpx prefix", "[httpx]" not in log and "[nmap]" in log)
            page.keyboard.press("Escape")
            page.get_by_role("searchbox", name="搜索资产").fill("no_matching_fixture_asset")
            page.get_by_role("button", name="列设置").click()
            page.get_by_label("标题", exact=True).uncheck()
            counts = page.locator("table.data").first.evaluate("t => ({headers:t.querySelectorAll('thead th').length,span:t.querySelector('tbody td').colSpan})")
            evidence["empty_table_columns"] = counts
            check("N7 empty row colspan follows visible columns", counts["headers"] == counts["span"])
            check("No browser JavaScript errors", not errors)
            check("No external browser requests", not external)
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (OUT / "browser-results.json").write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks, "evidence": evidence, "errors": errors, "blocked_external_requests": external}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if checks and all(checks.values()) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

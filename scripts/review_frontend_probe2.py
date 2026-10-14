# -*- coding: utf-8 -*-
"""决定性实验：MutationObserver 追踪 Enter 后 drawer 是否曾出现又被移除。"""
import http.server
import json
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

ROOT = Path(r"D:\Desktop\asm\frontend\dist")
BASE = "http://127.0.0.1:6271"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, *a):
        pass


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 6271), QuietHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")

        # 记录 DOM 变化 + 点击事件
        page.evaluate(
            """() => {
                window.__muts = [];
                const obs = new MutationObserver(list => {
                    for (const m of list) {
                        for (const n of m.addedNodes) window.__muts.push({op:'add', t: n.nodeType===1? n.tagName+'.'+n.className : '#'+n.nodeType, when: performance.now()});
                        for (const n of m.removedNodes) window.__muts.push({op:'del', t: n.nodeType===1? n.tagName+'.'+n.className : '#'+n.nodeType, when: performance.now()});
                    }
                });
                obs.observe(document.getElementById('root'), {childList: true, subtree: true});
                window.__clicks = [];
                document.addEventListener('click', e => window.__clicks.push({t: e.target.tagName + '.' + (e.target.className||''), x: e.clientX, y: e.clientY, when: performance.now()}), true);
            }"""
        )
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        page.evaluate("window.__muts.length = 0")
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        muts = page.evaluate("window.__muts")
        clicks = page.evaluate("window.__clicks")
        drawer = page.evaluate("document.querySelectorAll('.drawer').length")
        print(f"drawer={drawer}", flush=True)
        print("clicks:", json.dumps(clicks), flush=True)
        print("mutations:", json.dumps(muts[:40]), flush=True)

        # 若 muts 中有 aside.drawer 的 add+del，说明曾渲染又被移除
        browser.close()
    srv.shutdown()


if __name__ == "__main__":
    main()

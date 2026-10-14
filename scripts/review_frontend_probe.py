# -*- coding: utf-8 -*-
"""定向实验：SearchModal Enter 键路径 vs 点击路径差异定位。"""
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

        # 在 document 上记录所有 keydown，观察 Enter 是否到达、目标是谁
        page.evaluate(
            "window.__keys = []; document.addEventListener('keydown', e => window.__keys.push({key: e.key, target: e.target.tagName + '.' + (e.target.className || '')}), true);"
        )
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        page.wait_for_timeout(700)
        keys = page.evaluate("window.__keys")
        print("keydown log:", json.dumps(keys), flush=True)
        drawer = page.evaluate("document.querySelectorAll('.drawer').length")
        bc = page.evaluate("document.querySelector('.breadcrumb') ? document.querySelector('.breadcrumb').innerText : '(none)'")
        print(f"native Enter -> drawer={drawer}, bc={bc!r}", flush=True)

        # 用合成事件重试
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.evaluate(
            """() => { const i = document.querySelector('.search-modal input');
                i.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true}));
                i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); }"""
        )
        page.wait_for_timeout(700)
        drawer2 = page.evaluate("document.querySelectorAll('.drawer').length")
        print(f"synthetic Enter -> drawer={drawer2}", flush=True)

        # 点击对照
        if drawer2:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.locator(".search-hit").nth(1).click()
        page.wait_for_timeout(700)
        drawer3 = page.evaluate("document.querySelectorAll('.drawer').length")
        print(f"click -> drawer={drawer3}", flush=True)

        # 若 Enter 路径失败但点击成功：检查 Enter 后 assetKey 状态是否又被清空
        if drawer3 == 1 and drawer == 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            page.evaluate("window.__sel = null")
            # 重新走 Enter 路径并连续采样 drawer 数量
            page.keyboard.press("Control+k")
            page.wait_for_timeout(300)
            page.locator(".search-modal input").fill("lab")
            page.wait_for_timeout(300)
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(150)
            page.keyboard.press("Enter")
            seen = []
            for i in range(12):
                page.wait_for_timeout(80)
                seen.append(page.evaluate("document.querySelectorAll('.drawer').length"))
            print("drawer samples after Enter:", seen, flush=True)

        browser.close()
    srv.shutdown()


if __name__ == "__main__":
    main()

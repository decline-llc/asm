# -*- coding: utf-8 -*-
"""复核转储：来源页徽章、报告总表、页签计数 —— 结果写入文本文件（避免控制台截断）。"""
import http.server
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

ROOT = Path(r"D:\Desktop\asm\frontend\dist")
OUT = Path(r"D:\Desktop\asm\docs\audits\review-artifacts")
BASE = "http://127.0.0.1:6271"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, *a):
        pass


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 6271), QuietHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    lines = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")

        # 1) 来源页全部卡片文本
        page.locator(".sidebar .nav-item", has_text="数据来源").click()
        page.wait_for_timeout(400)
        cards = page.locator("main .panel").all_inner_texts()
        for c in cards:
            lines.append("SOURCE CARD: " + c.replace("\n", " | ")[:400])

        # 2) 报告中心：工程明细总表 + CSV 导出
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(400)
        page.locator(".tabs button", has_text="工程明细").click()
        page.wait_for_timeout(300)
        page.locator(".filter-bar button", has_text="总表").click()
        page.wait_for_timeout(300)
        rows = page.locator("table.data tbody tr").all_inner_texts()
        lines.append(f"MASTER ROW COUNT: {len(rows)}")
        for r in rows:
            lines.append("MASTER ROW: " + r.replace("\n", " | ")[:220])
        with page.expect_download() as dl:
            page.get_by_role("button", name="下载本表 CSV（演示数据导出）").click()
        d = dl.value
        pth = OUT / "report-master-export.csv"
        d.save_as(str(pth))
        csv_text = pth.read_text(encoding="utf-8-sig")
        lines.append(f"MASTER CSV ROWS: {len(csv_text.splitlines()) - 1}")
        lines.append("MASTER CSV HEADERS: " + csv_text.splitlines()[0])
        for ln in csv_text.splitlines()[1:]:
            lines.append("MASTER CSV ROW: " + ln[:200])
        shop = any("shop.example.org" in ln for ln in csv_text.splitlines())
        tr50 = any("198.51.100.50" in ln for ln in csv_text.splitlines())
        cloudn = sum(1 for ln in csv_text.splitlines()[1:] if ln.split(",")[1] == "cloud.example.com" and ln.split(",")[2] == "443")
        lines.append(f"MASTER CSV contains shop: {shop}; 198.51.100.50: {tr50}; cloud|443 rows: {cloudn}")

        # 3) 资产页签计数与 D+ 是否出现
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(400)
        tabs = page.locator(".tabs button").all_inner_texts()
        lines.append("ASSET TABS: " + " / ".join(t.replace(chr(10), "=") for t in tabs))
        for tabname in ["服务资产", "Web 页面", "IP", "隔离候选"]:
            page.locator(".tabs button", has_text=tabname).click()
            page.wait_for_timeout(300)
            rows = page.locator("table.data tbody tr").all_inner_texts()
            lines.append(f"TAB [{tabname}] rows={len(rows)}")
            for r in rows[:30]:
                lines.append(f"  {r.replace(chr(10), ' | ')[:150]}")

        # 4) 概览优先队列前 5 项与统计口径脚注
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        feet = page.locator(".stat-card .foot").all_inner_texts()
        lines.append("STAT FEET: " + " / ".join(feet))

        browser.close()
    srv.shutdown()
    out = OUT / "recheck-dump.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"written {out} with {len(lines)} lines")


if __name__ == "__main__":
    main()

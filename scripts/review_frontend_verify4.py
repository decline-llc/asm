# -*- coding: utf-8 -*-
"""GLM 审阅用：运行时验证第四部分（收尾）。"""
import http.server
import json
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

ROOT = Path(r"D:\Desktop\asm\frontend\dist")
SHOTS = Path(r"D:\Desktop\asm\docs\audits\review-artifacts")
BASE = "http://127.0.0.1:6271"
results = {}


def note(msg):
    print(msg, flush=True)


def shoot(page, name):
    p = SHOTS / f"{name}.png"
    page.screenshot(path=str(p), full_page=True)
    note(f"[shot] {p.name}")


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
        errors = []
        page.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.goto(BASE, wait_until="networkidle")

        # ============ 1. 键盘 Enter 搜索跳转：不同视图分别测 ============
        for view_name, nav_text in [("overview", "项目概览"), ("tasks", "调查任务"), ("sources", "数据来源"), ("assets", "资产探索")]:
            page.locator(".sidebar .nav-item", has_text=nav_text).click()
            page.wait_for_timeout(300)
            page.keyboard.press("Control+k")
            page.wait_for_timeout(300)
            page.locator(".search-modal input").fill("lab")
            page.wait_for_timeout(300)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            page.wait_for_timeout(700)
            d = page.evaluate("document.querySelectorAll('.drawer').length")
            bc = page.locator(".breadcrumb").inner_text() if page.locator(".breadcrumb").count() else "(none)"
            note(f"keyboard Enter search from {view_name}: drawer={d}, breadcrumb={bc!r}")
            results[f"kb_search_{view_name}"] = {"drawer": d, "breadcrumb": bc}
            if d:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)

        # 控制台/页面错误（关键：找出 Enter 路径的错误）
        if errors:
            note("ERRORS so far:")
            for e in errors[:30]:
                note("  " + str(e))
        results["errors_after_kb"] = [str(e) for e in errors[:30]]

        # ============ 2. 畸形 localStorage 崩溃复现 + 可恢复性 ============
        page.evaluate("localStorage.setItem('asm-workbench-local-v1', JSON.stringify({demoTasks:[{id:'X', name:'x'}], leadStatus:{}, leadNotes:{}, leadHistory:{}, settings:{reduceMotion:false}}))")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(600)
        blank = page.evaluate("document.querySelectorAll('.stat-card').length")
        err2 = [str(e) for e in errors]
        note(f"malformed demoTasks -> stat-cards: {blank}; new errors: {err2[-3:] if err2 else 'none'}")
        results["malformed_crash"] = {"stat_cards": blank, "errors": err2[-5:]}
        shoot(page, "25-malformed-localstorage")
        # reload 后仍然崩溃？
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(600)
        blank2 = page.evaluate("document.querySelectorAll('.stat-card').length")
        note(f"after reload, still blank: {blank2 == 0}")
        results["malformed_persists"] = blank2 == 0
        # 清理
        page.evaluate("localStorage.removeItem('asm-workbench-local-v1')")

        # ============ 3. 窄屏 390 ============
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(500)
        shoot(page, "21b-mobile-390-assets")
        ov = page.evaluate("() => { const t = document.querySelector('.table-wrap'); return t ? [t.scrollWidth, t.clientWidth] : null }")
        note(f"mobile table-wrap: {ov}")
        results["mobile_table_overflow"] = ov
        sb = page.evaluate("() => { const s = document.querySelector('.sidebar'); const r = s.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height)] }")
        note(f"mobile sidebar [top,height]: {sb}")
        results["mobile_sidebar_pos"] = sb
        page.locator("table.data tbody tr").first.click()
        page.wait_for_timeout(400)
        dw = page.evaluate("getComputedStyle(document.querySelector('.drawer')).width")
        note(f"mobile drawer width: {dw}")
        results["mobile_drawer_width"] = dw
        shoot(page, "22b-mobile-390-drawer")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(400)
        shoot(page, "23b-mobile-390-review")
        # 移动端新建调查（关键操作）
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(400)
        shoot(page, "26-mobile-390-tasks")

        # 1024 视口
        page.set_viewport_size({"width": 1024, "height": 768})
        page.wait_for_timeout(400)
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        shoot(page, "24b-1024-overview")

        # ============ 4. 图谱视图基本可用性（桌面） ============
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator(".sidebar .nav-item", has_text="关系图谱").click()
        page.wait_for_timeout(500)
        nodes = page.evaluate("document.querySelectorAll('.gnode').length")
        edges = page.evaluate("document.querySelectorAll('g[opacity] line').length")
        note(f"graph nodes: {nodes}, edges: {edges}")
        results["graph_nodes_edges"] = [nodes, edges]
        shoot(page, "27-graph")
        # 点击服务节点聚焦
        page.locator(".gnode", has_text="lab:443").click()
        page.wait_for_timeout(300)
        side = page.locator(".panel", has_text="邻域关系").count()
        note(f"focus side card: {side}")
        results["graph_focus_card"] = side
        shoot(page, "28-graph-focus")
        # 双击打开抽屉
        page.locator(".gnode", has_text="lab:443").dblclick()
        page.wait_for_timeout(400)
        d = page.evaluate("document.querySelectorAll('.drawer').length")
        note(f"dblclick service node -> drawer: {d}")
        results["graph_dblclick_drawer"] = d
        if d:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

        # ============ 5. 重置演示（正常路径） ============
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.locator("input[aria-label='添加备注']").fill("将被重置")
        page.get_by_role("button", name="添加").click()
        page.wait_for_timeout(300)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="重置演示").click()
        page.wait_for_timeout(600)
        ls = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"ls after reset: {ls!r}")
        results["ls_after_reset"] = ls
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        stats = page.locator(".stat-card .value").all_inner_texts()
        note(f"stats after reset: {stats}")
        results["stats_after_reset"] = stats

        if errors:
            note("ALL ERRORS:")
            for e in errors[:30]:
                note("  " + str(e))
        results["page_errors"] = [str(e) for e in errors[:30]]
        browser.close()
    srv.shutdown()
    (SHOTS / "runtime-results4.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    note("saved runtime-results4.json")


if __name__ == "__main__":
    main()

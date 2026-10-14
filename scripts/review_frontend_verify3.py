# -*- coding: utf-8 -*-
"""GLM 审阅用：运行时验证第三部分（定向复现）。"""
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

        # ============ 1. 搜索跳转抽屉之谜：DOM dump ============
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(300)
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        dominfo = page.evaluate(
            """() => ({
                asideCount: document.querySelectorAll('aside').length,
                drawerCount: document.querySelectorAll('.drawer').length,
                dialogCount: document.querySelectorAll('[role=dialog]').length,
                overlayCount: document.querySelectorAll('.drawer-overlay').length,
                rootHtml: document.querySelector('#root').innerHTML.slice(0, 300),
                activeEl: document.activeElement ? document.activeElement.tagName : 'none'
            })"""
        )
        note(f"search dom dump: {json.dumps(dominfo, ensure_ascii=False)[:500]}")
        results["search_dom_dump"] = dominfo
        shoot(page, "19-search-drawer-mystery")
        # 若抽屉确实没开，点一次搜索结果（鼠标点击）验证是否可开
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.locator(".search-hit").nth(1).click()
        page.wait_for_timeout(600)
        d2 = page.evaluate("document.querySelectorAll('.drawer').length")
        note(f"search click hit -> drawer count: {d2}")
        results["search_click_drawer"] = d2
        if d2:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

        # ============ 2. cloud 第一行(.22) 点击抽屉 IP ============
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(300)
        page.locator("input[aria-label='搜索资产']").fill("cloud.example.com")
        page.wait_for_timeout(300)
        r1_ip = page.locator("table.data tbody tr").first.locator("td").nth(1).inner_text()
        note(f"row1 table shows ip: {r1_ip!r}")
        page.locator("table.data tbody tr").first.click()
        page.wait_for_timeout(400)
        dds = page.locator(".drawer .drawer-body dd").all_inner_texts()
        note(f"row1(.22) -> drawer dds(first 3): {dds[:3]}")
        results["cloud_row1_table_ip"] = r1_ip
        results["cloud_row1_drawer_dds"] = dds[:3]
        shoot(page, "20-cloud-row1-drawer")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.locator("input[aria-label='搜索资产']").fill("")
        page.wait_for_timeout(200)

        # ============ 3. 「查看筛选后的资产列表」按钮 ============
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="查看筛选后的资产列表").click()
        page.wait_for_timeout(400)
        cur_view = page.locator(".page-title h2").inner_text()
        cnt = page.locator(".count-note").inner_text() if page.locator(".count-note").count() else "(none)"
        sel_co = page.locator("select[aria-label='按公司筛选']").input_value() if page.locator("select[aria-label='按公司筛选']").count() else "(no select)"
        note(f"button -> view: {cur_view!r}; count-note: {cnt!r}; company filter value: {sel_co!r}")
        results["overview_btn_view"] = cur_view
        results["overview_btn_filter"] = {"count": cnt, "company": sel_co}

        # ============ 4. 备注与已复核计数口径 ============
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.locator("input[aria-label='添加备注']").fill("审阅验证备注C3")
        page.get_by_role("button", name="添加").click()
        page.wait_for_timeout(300)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        # reload 后 view 保持 review（selection 不持久化 -> 回到 overview）
        cur = page.locator(".page-title h2").inner_text()
        note(f"view after reload (fresh page state): {cur!r}")
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        wt = page.locator(".review-layout .panel").last.inner_text()
        note(f"note persisted after reload+nav: {'审阅验证备注C3' in wt}")
        results["note_persisted"] = "审阅验证备注C3" in wt
        results["view_after_reload"] = cur
        # 标记已复核
        page.get_by_role("button", name="已复核").first.click()
        page.wait_for_timeout(300)
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        stats = page.locator(".stat-card .value").all_inner_texts()
        note(f"overview stats after 1 reviewed: {stats}")
        results["stats_after_reviewed"] = stats
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(300)
        page.locator(".tabs button", has_text="汇报视图").click()
        page.wait_for_timeout(200)
        s = page.locator(".panel-body").first.inner_text()
        note("report summary(first 240): " + s[:240].replace("\n", "|"))
        results["report_summary_after_reviewed"] = s[:240]

        # ============ 5. localStorage 损坏容错 ============
        page.evaluate("localStorage.setItem('asm-workbench-local-v1', '{invalid json')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)
        ok = page.locator(".stat-card .value").count()
        note(f"app renders after corrupt localStorage: {ok > 0}")
        results["corrupt_ls_ok"] = ok > 0
        page.evaluate("localStorage.setItem('asm-workbench-local-v1', JSON.stringify({leadStatus:{unknown:'reviewed'}, demoTasks:[{bad:'shape'}], settings:{}}))")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)
        ok2 = page.locator(".stat-card .value").count()
        stale = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"app renders after odd-shape local state: {ok2 > 0}; state: {(stale or '')[:120]!r}")
        results["odd_shape_ls_ok"] = ok2

        # ============ 6. 窄屏 ============
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(500)
        shoot(page, "21-mobile-390-assets")
        page.locator("table.data tbody tr").first.click()
        page.wait_for_timeout(400)
        dw = page.evaluate("getComputedStyle(document.querySelector('.drawer')).width")
        note(f"mobile drawer width: {dw}")
        results["mobile_drawer_width"] = dw
        shoot(page, "22-mobile-390-drawer")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        ov = page.evaluate("() => { const t = document.querySelector('.table-wrap'); return t ? [t.scrollWidth, t.clientWidth] : null }")
        note(f"mobile table-wrap: {ov}")
        results["mobile_table_overflow"] = ov
        sb = page.evaluate("() => { const s = document.querySelector('.sidebar'); const r = s.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height)] }")
        note(f"mobile sidebar [top,height]: {sb}")
        results["mobile_sidebar_pos"] = sb
        # 移动端顶部导航可见性
        nav_ok = page.evaluate("() => { const n = document.querySelector('.sidebar nav'); const r = n.getBoundingClientRect(); return r.width > 100 && r.height > 20 }")
        note(f"mobile nav visible: {nav_ok}")
        results["mobile_nav_visible"] = nav_ok
        # 移动端优先核对关键操作：复核页
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(400)
        shoot(page, "23-mobile-390-review")

        # 1024
        page.set_viewport_size({"width": 1024, "height": 768})
        page.wait_for_timeout(400)
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        shoot(page, "24-1024-overview")

        # ============ 7. 重置演示 ============
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="重置演示").click()
        page.wait_for_timeout(600)
        ls2 = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"ls after reset: {ls2!r}")
        results["ls_after_reset"] = ls2
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        stats2 = page.locator(".stat-card .value").all_inner_texts()
        note(f"stats after reset: {stats2}")
        results["stats_after_reset"] = stats2

        # ============ 8. XSS 安全渲染抽查（标题含 <script> 的资产不存在——检查现有数据渲染方式） ============
        # 概念检查：所有文本均经 React 转义。检查 lead L009 的目标文本渲染
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        body_has_script = page.evaluate("() => !!document.querySelector('.review-layout script')")
        note(f"script tag leaked in review: {body_has_script}")
        results["no_script_leak"] = not body_has_script

        if errors:
            note("ERRORS:")
            for e in errors[:20]:
                note("  " + str(e))
        results["page_errors"] = [str(e) for e in errors[:20]]
        browser.close()
    srv.shutdown()
    (SHOTS / "runtime-results3.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    note("saved runtime-results3.json")


if __name__ == "__main__":
    main()

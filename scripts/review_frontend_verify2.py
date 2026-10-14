# -*- coding: utf-8 -*-
"""GLM 审阅用：运行时验证第二部分（断点续跑）。
覆盖：任务推进后的状态一致性、向导创建、持久化、重置、窄屏、
全局搜索跳转抽屉、cloud 重复主键抽屉 IP。"""
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
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:6271"

log = []


def note(msg):
    log.append(str(msg))
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
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.goto(BASE, wait_until="networkidle")

        # ---------- 搜索跳转（从报告中心这一非内联视图） ----------
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(300)
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        found = False
        for _ in range(20):
            page.wait_for_timeout(100)
            if page.locator(".drawer").count() > 0:
                found = True
                break
        note(f"search->openAsset from reports view: drawer appeared = {found}")
        results["search_drawer_from_reports"] = found
        if not found:
            dom = page.evaluate("document.querySelector('#root') ? document.querySelector('#root').children.length : -1")
            note(f"root children count: {dom}")
        bc = page.locator(".breadcrumb").inner_text() if page.locator(".breadcrumb").count() else "(none)"
        note(f"breadcrumb: {bc!r}")
        results["search_breadcrumb"] = bc
        if found:
            shoot(page, "10b-search-drawer")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

        # ---------- cloud 重复主键：第二行抽屉 IP ----------
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(300)
        page.locator("input[aria-label='搜索资产']").fill("cloud.example.com")
        page.wait_for_timeout(300)
        rows = page.locator("table.data tbody tr")
        note(f"cloud rows: {rows.count()}")
        r2_ip = rows.nth(1).locator("td").nth(1).inner_text()
        note(f"row2 table ip: {r2_ip!r}")
        rows.nth(1).click()
        page.wait_for_timeout(300)
        # 概况页签 dd 列表：主键、选用地址、归属企业……
        dds = page.locator(".drawer .drawer-body dd").all_inner_texts()
        note(f"drawer dds(first 6): {dds[:6]}")
        results["cloud_row2_table_ip"] = r2_ip
        results["cloud_row2_drawer_dds"] = dds[:6]
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        page.locator("input[aria-label='搜索资产']").fill("")
        page.wait_for_timeout(200)

        # ---------- 任务推进后的状态一致性（重放链路 B 核心段） ----------
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        page.locator(".lead-item", has_text="RUN-20261009-01").first.click()
        page.wait_for_timeout(400)
        # 重试 + 推进
        retry = page.get_by_role("button", name="重试（模拟）")
        if retry.count():
            retry.first.click()
            page.wait_for_timeout(300)
        adv = page.get_by_role("button", name="模拟推进一阶段")
        if adv.count():
            adv.click()
            page.wait_for_timeout(400)
        head_txt = page.locator(".panel", has_text="阶段流程").first.inner_text()
        note("task panel after retry+advance (first 600): " + head_txt[:600].replace("\n", "|"))
        results["task_panel_after"] = head_txt[:600]
        shoot(page, "12b-task-after-advance")
        # 任务状态徽章（卡片上）—— 返回列表查看
        page.get_by_role("button", name="返回任务列表").click()
        page.wait_for_timeout(300)
        cards = page.locator(".lead-item").all_inner_texts()
        note(f"task cards after advance: {[c[:70] for c in cards]}")
        results["task_cards_after"] = [c[:100] for c in cards]

        # ---------- 向导创建演示任务 ----------
        page.get_by_role("button", name="新建调查（演示）").first.click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="下一步").click()  # step0 -> 1
        page.wait_for_timeout(200)
        scope_tbl = page.locator(".modal table.data").inner_text()
        note("wizard scope table: " + scope_tbl.replace("\n", "|")[:240])
        results["wizard_scope"] = scope_tbl[:240]
        page.get_by_role("button", name="下一步").click()  # 1 -> 2
        page.wait_for_timeout(200)
        page.get_by_role("button", name="下一步").click()  # 2 -> 3
        page.wait_for_timeout(200)
        summ = page.locator(".modal dl.fields").inner_text()
        note("wizard summary: " + summ.replace("\n", "|")[:300])
        results["wizard_summary"] = summ[:300]
        # 向导 Esc 是否可关
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        wiz_open = page.locator(".modal").count()
        note(f"wizard Esc closes modal? {wiz_open == 0}")
        results["wizard_esc_close"] = wiz_open == 0
        if wiz_open:
            page.get_by_role("button", name="创建演示任务").click()
            page.wait_for_timeout(500)
        shoot(page, "13b-wizard")
        created = page.locator(".panel-head h3").first.inner_text() if page.locator(".panel-head h3").count() else ""
        note(f"created/first task head: {created!r}")
        results["created_task_head"] = created

        # ---------- 持久化 ----------
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        ls = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"localStorage after reload: {(ls or '')[:200]!r}")
        results["ls_after_reload"] = (ls or "")[:200]
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        demo_n = page.locator(".lead-item", has_text="DEMO-").count()
        note(f"demo tasks persisted: {demo_n}")
        results["demo_tasks_persisted"] = demo_n

        # 备注持久化
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.locator("input[aria-label='添加备注']").fill("审阅验证备注")
        page.get_by_role("button", name="添加").click()
        page.wait_for_timeout(300)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        wt = page.locator(".review-layout .panel").last.inner_text()
        note(f"note persisted after reload: {'审阅验证备注' in wt}")
        results["note_persisted"] = "审阅验证备注" in wt
        # 标记已复核后概览计数变化
        page.get_by_role("button", name="已复核").first.click()
        page.wait_for_timeout(300)
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        stats = page.locator(".stat-card .value").all_inner_texts()
        note(f"stats after marking one lead reviewed: {stats}")
        results["stats_after_reviewed"] = stats
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(300)
        page.locator(".tabs button", has_text="汇报视图").click()
        page.wait_for_timeout(200)
        s2 = page.locator(".panel-body").first.inner_text()
        note("report summary after reviewed(first 200): " + s2[:200].replace("\n", "|"))
        results["report_summary_after_reviewed"] = s2[:200]

        # ---------- 窄屏 390 ----------
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        shoot(page, "14b-mobile-390-reports")
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(500)
        shoot(page, "15b-mobile-390-assets")
        page.locator("table.data tbody tr").first.click()
        page.wait_for_timeout(400)
        dw = page.evaluate("getComputedStyle(document.querySelector('.drawer')).width")
        note(f"mobile drawer width: {dw}")
        results["mobile_drawer_width"] = dw
        shoot(page, "16b-mobile-390-drawer")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        ov = page.evaluate("() => { const t = document.querySelector('.table-wrap'); return t ? [t.scrollWidth, t.clientWidth] : null }")
        note(f"mobile table-wrap [scrollWidth, clientWidth]: {ov}")
        results["mobile_table_overflow"] = ov
        # 移动端侧栏形态
        sb = page.evaluate("() => { const s = document.querySelector('.sidebar'); const r = s.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height)] }")
        note(f"mobile sidebar [top, height]: {sb}")
        results["mobile_sidebar_pos"] = sb

        # 1024
        page.set_viewport_size({"width": 1024, "height": 768})
        page.wait_for_timeout(400)
        shoot(page, "17b-1024-assets")

        # ---------- 重置演示 ----------
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="重置演示").click()
        page.wait_for_timeout(600)
        ls2 = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"localStorage after reset: {ls2!r}")
        results["ls_after_reset"] = ls2
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        stats2 = page.locator(".stat-card .value").all_inner_texts()
        note(f"stats after reset: {stats2}")
        results["stats_after_reset"] = stats2
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        demo_after = page.locator(".lead-item", has_text="DEMO-").count()
        note(f"demo tasks after reset: {demo_after}")
        results["demo_tasks_after_reset"] = demo_after
        shoot(page, "18b-after-reset")

        if errors:
            note("PAGE ERRORS:")
            for e in errors[:20]:
                note("  " + str(e))
        results["page_errors"] = [str(e) for e in errors[:20]]
        browser.close()
    srv.shutdown()
    out = SHOTS / "runtime-results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    note(f"results saved: {out}")


if __name__ == "__main__":
    main()

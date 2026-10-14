# -*- coding: utf-8 -*-
"""GLM 审阅用：ASM Workbench 前端运行时验证（链路 A / 链路 B + 附加检查）。
仅在本地演示构建 dist/ 上运行，不触发任何真实扫描或第三方 API。
"""
import http.server
import json
import socket
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
    log.append(msg)
    print(msg, flush=True)


def free_port_check(port):
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))
    return True


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, *a):
        pass


def start_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 6271), QuietHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def shoot(page, name):
    p = SHOTS / f"{name}.png"
    page.screenshot(path=str(p), full_page=True)
    note(f"[shot] {p.name}")


def read_downloads(page, timeout=4000):
    """收集本次会话触发的下载内容。"""
    return page.evaluate("window.__dl || null")


def main():
    srv = start_server()
    note(f"server on {BASE}")
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        # ---------------- 首屏 ----------------
        page.goto(BASE, wait_until="networkidle")
        note(f"title: {page.title()}")
        stats = page.locator(".stat-card .value").all_inner_texts()
        labels = page.locator(".stat-card .label").all_inner_texts()
        note(f"overview stats: {list(zip(labels, stats))}")
        results["stats_labels"] = list(zip(labels, stats))
        shoot(page, "01-overview-1440")
        pipeline_txt = page.locator(".pipeline").inner_text()
        note(f"pipeline: {pipeline_txt!r}")
        results["pipeline_text"] = pipeline_txt
        recent = page.locator(".lead-item").all_inner_texts()
        note(f"recent/priority items count: {len(recent)}")
        task_rows = page.locator("main .grid.cols-2 .panel").nth(1).locator(".lead-item").all_inner_texts()
        note(f"recent tasks: {task_rows}")
        results["recent_tasks"] = task_rows

        # ---------------- 链路 A ----------------
        # A1: 点击 DNS 待核对项 L001（建议优先核对队列第一条应为 high 级）
        pri = page.locator("main section.panel").nth(1).locator(".lead-item")
        first = pri.first.inner_text()
        note(f"priority first: {first!r}")
        pri.first.click()
        page.wait_for_timeout(300)
        # 现在应在证据复核页
        note(f"view breadcrumb hidden?: {page.locator('.breadcrumb').count()}")
        workbench = page.locator(".review-layout .panel").last.inner_text()
        note("workbench(first 400): " + workbench[:400].replace("\n", "|"))
        results["lead_workbench_head"] = workbench[:400]
        shoot(page, "02-review-L001")

        # A2: 打开关联资产详情
        page.get_by_role("button", name="打开关联资产详情").click()
        page.wait_for_timeout(400)
        drawer_head = page.locator(".drawer .drawer-head h3").inner_text()
        note(f"drawer head: {drawer_head!r}")
        results["drawer_head"] = drawer_head

        # A3: 证据页签（默认应为「概况」— 先点「证据」）
        page.locator(".drawer .tabs button", has_text="证据").click()
        page.wait_for_timeout(200)
        lens = page.locator(".drawer .lens").inner_text()
        note("lens(first 300): " + lens[:300].replace("\n", "|"))
        results["lens_text"] = lens[:300]
        shoot(page, "03-drawer-evidence-lens")

        # A4: DNS 页签
        page.locator(".drawer .tabs button", has_text="DNS").click()
        page.wait_for_timeout(200)
        dns_txt = page.locator(".drawer .drawer-body").inner_text()
        note("dns tab(first 500): " + dns_txt[:500].replace("\n", "|"))
        results["dns_tab_text"] = dns_txt[:500]
        shoot(page, "04-drawer-dns")

        # A5: Web 与截图页签
        page.locator(".drawer .tabs button", has_text="Web 与截图").click()
        page.wait_for_timeout(200)
        shot_txt = page.locator(".drawer .drawer-body").inner_text()
        note("web tab(first 300): " + shot_txt[:300].replace("\n", "|"))
        results["web_tab_text"] = shot_txt[:300]

        # Esc 关闭抽屉，检查焦点是否恢复
        _focused_before = page.evaluate("document.activeElement.className")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        drawer_gone = page.locator(".drawer").count()
        focused_after = page.evaluate("document.activeElement ? (document.activeElement.tagName + '.' + document.activeElement.className) : 'none'")
        note(f"esc closed drawer: {drawer_gone == 0}; focus after close: {focused_after}")
        results["esc_close"] = drawer_gone == 0
        results["focus_after_close"] = focused_after

        # A6: 资产表组合筛选 公司=澄川云 + 来源=FOFA
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(300)
        tabs = page.locator(".tabs button").all_inner_texts()
        note(f"assets tabs: {tabs}")
        results["asset_tabs"] = tabs
        page.locator("select[aria-label='按公司筛选']").select_option(label="澄川云")
        page.wait_for_timeout(200)
        page.locator("select[aria-label='按来源筛选']").select_option(label="FOFA")
        page.wait_for_timeout(200)
        cnt = page.locator(".count-note").inner_text()
        note(f"filtered count note: {cnt!r}")
        rows = page.locator("table.data tbody tr").all_inner_texts()
        note(f"filtered rows({len(rows)}): {[r[:60] for r in rows]}")
        results["filtered_rows"] = [r[:80] for r in rows]
        shoot(page, "05-assets-filtered")

        # A7: CSV 导出（当前结果）
        with page.expect_download() as dl_info:
            page.get_by_role("button", name="导出当前结果 CSV").click()
        dl = dl_info.value
        csv_path = SHOTS / "chainA-export.csv"
        dl.save_as(str(csv_path))
        csv_text = Path(csv_path).read_text(encoding="utf-8-sig")
        note(f"exported csv lines({len(csv_text.splitlines())}): {csv_text[:300]!r}")
        results["chainA_csv_preview"] = csv_text[:300]
        results["chainA_csv_rows"] = len(csv_text.splitlines()) - 1

        # 附加：验证导出是否含重复主键
        import csv as csvmod
        import io
        rdr = list(csvmod.reader(io.StringIO(csv_text)))
        keys = [f"{r[1]}|{r[2]}|{r[3]}" for r in rdr[1:]]
        dup = [k for k in set(keys) if keys.count(k) > 1]
        note(f"csv primary-key duplicates: {dup!r}")
        results["csv_dup_keys"] = dup

        # ---------------- 附加检查 ----------------
        # B1: 域名页签点击 iot.example.com（无 443 资产，应无反应）
        page.locator("select[aria-label='按公司筛选']").select_option(label="公司：全部")
        page.locator("select[aria-label='按来源筛选']").select_option(label="来源：全部")
        page.locator(".tabs button", has_text="域名").click()
        page.wait_for_timeout(200)
        page.locator("table.data tbody tr", has_text="iot.example.com").click()
        page.wait_for_timeout(400)
        drawer_open = page.locator(".drawer").count()
        note(f"click domain iot.example.com -> drawer opened? {drawer_open}")
        results["domain_click_no_drawer"] = drawer_open
        # 域名页签点击 shop.example.org（D+ 资产）
        page.locator("table.data tbody tr", has_text="shop.example.org").click()
        page.wait_for_timeout(400)
        drawer_open2 = page.locator(".drawer").count()
        if drawer_open2:
            head2 = page.locator(".drawer .drawer-head h3").inner_text()
            conf = page.locator(".drawer .drawer-body .badge").first.inner_text()
            note(f"click domain shop.example.org -> drawer: {head2!r} conf-badge: {conf!r}")
            results["domain_shop_drawer"] = {"head": head2, "conf": conf}
            page.keyboard.press("Escape")
        shoot(page, "06-assets-domains")

        # B2: IP 页签是否包含 D+ 资产 IP
        page.locator(".tabs button", has_text="IP").click()
        page.wait_for_timeout(200)
        ip_rows = page.locator("table.data tbody tr").all_inner_texts()
        note(f"ip rows: {[r[:70] for r in ip_rows]}")
        results["ip_rows"] = [r[:80] for r in ip_rows]
        has_192_0_2_200 = any("192.0.2.200" in r for r in ip_rows)
        note(f"IP tab contains quarantined 192.0.2.200? {has_192_0_2_200}")
        results["ip_tab_has_quarantine_ip"] = has_192_0_2_200
        if has_192_0_2_200:
            page.locator("table.data tbody tr", has_text="192.0.2.200").click()
            page.wait_for_timeout(300)
            h = page.locator(".drawer .drawer-head h3").inner_text() if page.locator(".drawer").count() else None
            note(f"click 192.0.2.200 row -> {h!r}")
            results["ip_click_quarantine_drawer"] = h
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

        # B3: 隔离候选页签
        page.locator(".tabs button", has_text="隔离候选").click()
        page.wait_for_timeout(200)
        q_rows = page.locator("table.data tbody tr").all_inner_texts()
        note(f"quarantine rows: {q_rows}")
        results["quarantine_rows"] = q_rows

        # B4: 双 CDN 行为：搜索 cloud.example.com，看两行同主键
        page.locator(".tabs button", has_text="服务资产").click()
        page.wait_for_timeout(200)
        page.locator("input[aria-label='搜索资产']").fill("cloud.example.com")
        page.wait_for_timeout(300)
        cloud_rows = page.locator("table.data tbody tr").all_inner_texts()
        note(f"cloud rows({len(cloud_rows)}): {[r[:70] for r in cloud_rows]}")
        results["cloud_rows"] = [r[:80] for r in cloud_rows]
        # 点击第二行（198.51.100.22）看抽屉显示哪个 IP
        if len(cloud_rows) >= 2:
            page.locator("table.data tbody tr").nth(1).click()
            page.wait_for_timeout(300)
            ip_in_drawer = page.locator(".drawer .drawer-body dd.mono").first.inner_text()
            note(f"cloud row2(198.51.100.22) -> drawer ip: {ip_in_drawer!r}")
            results["cloud_row2_drawer_ip"] = ip_in_drawer
            page.keyboard.press("Escape")
        shoot(page, "07-assets-cloud-dup")

        # B5: 数据来源页
        page.locator(".sidebar .nav-item", has_text="数据来源").click()
        page.wait_for_timeout(300)
        src_cards = page.locator("main .panel").all_inner_texts()
        fofa = [c for c in src_cards if c.startswith("FOFA")]
        httpx_c = [c for c in src_cards if "httpx" in c[:30]]
        note(f"FOFA card: {fofa[0][:200]!r}" if fofa else "no FOFA card")
        note(f"httpx card: {httpx_c[0][:200]!r}" if httpx_c else "no httpx card")
        results["fofa_card"] = fofa[0][:200] if fofa else None
        results["httpx_card"] = httpx_c[0][:200] if httpx_c else None
        shoot(page, "08-sources")

        # B6: 报告中心（工程明细 + 汇报视图）
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(300)
        page.locator(".tabs button", has_text="工程明细").click()
        page.wait_for_timeout(200)
        page.locator(".filter-bar button", has_text="总表").click()
        page.wait_for_timeout(200)
        master_rows = page.locator("table.data tbody tr").count()
        master_note = page.locator(".report-table-note").inner_text()
        note(f"master rows: {master_rows}; note: {master_note!r}")
        results["master_rows"] = master_rows
        # 汇报视图中的新增计数
        page.locator(".tabs button", has_text="汇报视图").click()
        page.wait_for_timeout(200)
        summary = page.locator(".panel-body").first.inner_text()
        note("report summary(first 400): " + summary[:400].replace("\n", "|"))
        results["report_summary"] = summary[:400]
        # 导出总表 CSV
        page.locator(".tabs button", has_text="工程明细").click()
        page.wait_for_timeout(200)
        with page.expect_download() as dl2:
            page.get_by_role("button", name="下载本表 CSV（演示数据导出）").click()
        d2 = dl2.value
        p2 = SHOTS / "report-master-export.csv"
        d2.save_as(str(p2))
        mcsv = Path(p2).read_text(encoding="utf-8-sig")
        mrdr = list(csvmod.reader(io.StringIO(mcsv)))
        note(f"master csv header: {mrdr[0]}")
        note(f"master csv row count: {len(mrdr)-1}; sample: {mrdr[1] if len(mrdr)>1 else None}")
        results["master_csv_header"] = mrdr[0]
        results["master_csv_rows"] = len(mrdr) - 1
        mkeys = [f"{r[1]}|{r[2]}" for r in mrdr[1:]]
        mdup = [k for k in set(mkeys) if mkeys.count(k) > 1]
        note(f"master csv dup host|port: {mdup!r}")
        results["master_csv_dup"] = mdup
        # 总表中 shop / 198.51.100.50 是否出现
        shop_in_master = any("shop.example.org" in r for r in mrdr)
        tr069 = any("198.51.100.50" in r for r in mrdr)
        note(f"shop in master: {shop_in_master}; 198.51.100.50 in master: {tr069}")
        results["master_contains_dplus"] = shop_in_master or tr069
        shoot(page, "09-reports")

        # B7: 全局搜索 Ctrl+K 键盘操作
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        sm = page.locator(".search-modal").count()
        note(f"search modal open: {sm}")
        page.locator(".search-modal input").fill("lab")
        page.wait_for_timeout(300)
        hits = page.locator(".search-hit").count()
        kinds = page.locator(".search-hit .kind").all_inner_texts()
        note(f"search hits for 'lab': {hits} kinds: {kinds}")
        results["search_hits_lab"] = {"count": hits, "kinds": kinds}
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        after_search = page.locator(".drawer .drawer-head h3").count()
        breadcrumb_txt = page.locator(".breadcrumb").inner_text() if page.locator(".breadcrumb").count() else "(none)"
        note(f"after search enter: drawer={after_search}, breadcrumb={breadcrumb_txt!r}")
        results["search_enter_breadcrumb"] = breadcrumb_txt
        if after_search:
            page.keyboard.press("Escape")
        shoot(page, "10-search-lab")

        # ---------------- 链路 B：任务模拟 ----------------
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        cards = page.locator(".lead-item").all_inner_texts()
        note(f"task cards: {[c[:80] for c in cards]}")
        results["task_cards"] = [c[:100] for c in cards]
        # 打开 RUN-20261009-01
        page.locator(".lead-item", has_text="RUN-20261009-01").first.click()
        page.wait_for_timeout(400)
        stage_txt = page.locator(".pipeline").inner_text()
        note("task stage pipeline: " + stage_txt.replace("\n", "|"))
        results["run0109_pipeline"] = stage_txt
        sub_table = page.locator("table.data").first.inner_text()
        note("subtasks(first 400): " + sub_table[:400].replace("\n", "|"))
        results["run0109_subtasks"] = sub_table[:400]
        shoot(page, "11-task-run0109")

        # 重试失败的 gowitness 子任务
        retry_btn = page.get_by_role("button", name="重试（模拟）")
        n_retry = retry_btn.count()
        note(f"retry buttons: {n_retry}")
        results["retry_buttons"] = n_retry
        if n_retry:
            retry_btn.first.click()
            page.wait_for_timeout(400)
            sub_after = page.locator("table.data").first.inner_text()
            note("subtasks after retry(first 260): " + sub_after[:260].replace("\n", "|"))
            results["subtasks_after_retry"] = sub_after[:260]
        # 模拟推进
        adv = page.get_by_role("button", name="模拟推进一阶段")
        if adv.count():
            adv.click()
            page.wait_for_timeout(400)
            stage_after = page.locator(".pipeline").inner_text()
            note("pipeline after advance: " + stage_after.replace("\n", "|"))
            results["pipeline_after_advance"] = stage_after
            status_badge = page.locator(".panel-head .badge").first.inner_text()
            note(f"task badge after advance: {status_badge!r}")
            results["task_badge_after_advance"] = status_badge
        shoot(page, "12-task-advanced")

        # 新建演示任务（四步向导）
        page.get_by_role("button", name="新建调查（演示）").first.click()
        page.wait_for_timeout(300)
        wiz_step0 = page.locator(".modal .wizard-steps").inner_text()
        note(f"wizard steps: {wiz_step0!r}")
        page.get_by_role("button", name="下一步").click()
        page.wait_for_timeout(200)
        scope_tbl = page.locator(".modal table.data").inner_text()
        note("wizard scope(first 200): " + scope_tbl[:200].replace("\n", "|"))
        page.get_by_role("button", name="下一步").click()
        page.wait_for_timeout(200)
        page.get_by_role("button", name="下一步").click()
        page.wait_for_timeout(200)
        summary_txt = page.locator(".modal dl.fields").inner_text()
        note("wizard summary(first 260): " + summary_txt[:260].replace("\n", "|"))
        results["wizard_summary"] = summary_txt[:260]
        page.get_by_role("button", name="创建演示任务").click()
        page.wait_for_timeout(500)
        new_task_head = page.locator(".panel-head h3").inner_text() if page.locator(".panel-head h3").count() else ""
        note(f"after create, task head: {new_task_head!r}")
        results["created_task_head"] = new_task_head
        shoot(page, "13-task-created")

        # ---------------- 刷新持久化验证 ----------------
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        ls = page.evaluate("JSON.stringify(Object.keys(JSON.parse(localStorage.getItem('asm-workbench-local-v1')||'{}')))")
        note(f"localStorage keys after reload: {ls}")
        results["localStorage_keys"] = ls
        # 任务仍在？
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        demo_badge = page.locator(".lead-item", has_text="DEMO-").count()
        note(f"demo tasks after reload: {demo_badge}")
        results["demo_tasks_after_reload"] = demo_badge

        # 复核备注持久化：去复核页添加备注
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.locator("input[aria-label='添加备注']").fill("审阅验证：已人工核对 demo 备注")
        page.get_by_role("button", name="添加").click()
        page.wait_for_timeout(300)
        note("note added")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        note_text = page.locator(".review-layout .panel").last.inner_text()
        has_note = "审阅验证" in note_text
        note(f"note persisted after reload: {has_note}")
        results["note_persisted"] = has_note

        # ---------------- 窄屏 390px ----------------
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(400)
        shoot(page, "14-mobile-390-review")
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(400)
        shoot(page, "15-mobile-390-assets")
        # 抽屉全屏？
        page.locator("table.data tbody tr").first.click()
        page.wait_for_timeout(400)
        dw = page.evaluate("getComputedStyle(document.querySelector('.drawer')).width")
        note(f"mobile drawer width: {dw}")
        results["mobile_drawer_width"] = dw
        shoot(page, "16-mobile-390-drawer")
        # 水平滚动检查：表格是否溢出
        overflow = page.evaluate("() => { const t = document.querySelector('.table-wrap'); return t ? {sw: t.scrollWidth, cw: t.clientWidth} : null }")
        note(f"mobile table-wrap scroll: {overflow}")
        results["mobile_table_overflow"] = overflow

        # 1024 视口
        page.set_viewport_size({"width": 1024, "height": 768})
        page.wait_for_timeout(400)
        shoot(page, "17-1024-assets")

        # ---------------- 重置演示 ----------------
        page.set_viewport_size({"width": 1440, "height": 900})
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.once("dialog", lambda d: d.accept())
        page.get_by_role("button", name="重置演示").click()
        page.wait_for_timeout(500)
        ls2 = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"localStorage after reset: {ls2!r}")
        results["ls_after_reset"] = ls2
        # 重置后概览
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(400)
        stats2 = page.locator(".stat-card .value").all_inner_texts()
        note(f"stats after reset: {stats2}")
        results["stats_after_reset"] = stats2
        shoot(page, "18-after-reset")

        if errors:
            note("PAGE ERRORS:")
            for e in errors[:20]:
                note("  " + e)
        results["page_errors"] = errors[:20]
        browser.close()
    srv.shutdown()
    out = SHOTS / "runtime-results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    note(f"results saved: {out}")


if __name__ == "__main__":
    main()

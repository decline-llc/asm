# -*- coding: utf-8 -*-
"""修复后验证：R1–R10 逐条 + 链路 A/B。
仅在本地演示构建 frontend/dist 上运行，不触发任何真实扫描或第三方 API。
"""
import csv as csvmod
import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright
import http.server

ROOT = Path(r"D:\Desktop\asm\frontend\dist")
# 沙箱下 docs\scripts\ 不可写；产物落到沙箱临时目录（可写）
SHOTS = Path(os.environ.get("ASM_FIX_SHOTS") or os.path.join(tempfile.gettempdir(), "asm-fix-artifacts"))
SHOTS.mkdir(parents=True, exist_ok=True)
PORT = 6291
BASE = f"http://127.0.0.1:{PORT}/?demo=1"

log = []
def note(m):
    log.append(m)
    print(m, flush=True)

class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)
    def log_message(self, *a):
        pass

def start_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Quiet)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv

def shoot(page, name):
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
    note(f"[shot] {name}.png")

results = {}
def check(key, cond, extra=""):
    results[key] = bool(cond)
    note(f"  [{'PASS' if cond else 'FAIL'}] {key} {extra}")

def main():
    srv = start_server()
    note(f"server on {BASE}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(f"console.{m.type}:{m.text}") if m.type == "error" else None)
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(400)

        # ============ 概览指标（R3/R8） ============
        note("== 概览 ==")
        labels = page.locator(".stat-card .label").all_inner_texts()
        values = page.locator(".stat-card .value").all_inner_texts()
        foots = page.locator(".stat-card .foot").all_inner_texts()
        stats = dict(zip([lbl.strip() for lbl in labels], values))
        note(f"  stats: {stats}")
        note(f"  foots: {foots}")
        # R8: 可信资产 = A/B + 双来源C = 15
        check("R8.可信资产=15", stats.get("可信资产") == "15", f"(实际 {stats.get('可信资产')})")
        # R3: 本轮新增可信资产（快照差分 = api:9090, lab:9200 = 2）
        check("R3.本轮新增可信资产=2", stats.get("本轮新增可信资产") == "2", f"(实际 {stats.get('本轮新增可信资产')})")

        # ============ 链路 A：L001 → 证据透镜 → DNS ============
        note("== 链路 A ==")
        page.locator("main section.panel").nth(1).locator(".lead-item").first.click()
        page.wait_for_timeout(300)
        page.get_by_role("button", name="打开关联资产详情").click()
        page.wait_for_timeout(500)
        check("A.抽屉打开", page.locator(".drawer").count() == 1)
        drawer_head = page.locator(".drawer .drawer-head h3").inner_text()
        note(f"  drawer head: {drawer_head}")
        # 证据页签
        page.locator(".drawer .tabs button", has_text="证据").click()
        page.wait_for_timeout(200)
        lens = page.locator(".drawer .lens")
        check("A.证据透镜三分栏", lens.count() == 1 and "原始观测" in lens.inner_text() and "选用结果" in lens.inner_text() and "采纳理由" in lens.inner_text())
        shoot(page, "A1-evidence-lens")
        # DNS 页签 fake-IP
        page.locator(".drawer .tabs button", has_text="DNS").click()
        page.wait_for_timeout(200)
        dns_txt = page.locator(".drawer .drawer-body").inner_text()
        check("A.DNS含fake-IP标注", "fake-IP" in dns_txt or "异常观测" in dns_txt)
        shoot(page, "A2-dns")

        # R10: 抽屉内 Tab 循环圈定（焦点不出抽屉）
        tab_leak = False
        for _ in range(12):
            page.keyboard.press("Tab")
            page.wait_for_timeout(60)
            inside = page.evaluate(
                "(() => { const d=document.querySelector('.drawer'); return d && d.contains(document.activeElement) })()"
            )
            if not inside:
                tab_leak = True
                break
        check("R10.抽屉内Tab循环不出容器", not tab_leak)
        # Shift+Tab 反向同样圈定
        for _ in range(12):
            page.keyboard.press("Shift+Tab")
            page.wait_for_timeout(60)
            inside = page.evaluate(
                "(() => { const d=document.querySelector('.drawer'); return d && d.contains(document.activeElement) })()"
            )
            if not inside:
                tab_leak = True
                break
        check("R10.Shift+Tab反向圈定", not tab_leak)

        # R4/R10: Esc 关闭抽屉，焦点恢复（不落在 BODY）
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        check("A.Esc关闭抽屉", page.locator(".drawer").count() == 0)
        focus_after = page.evaluate("document.activeElement ? document.activeElement.tagName : 'none'")
        note(f"  focus after Esc: {focus_after}")
        check("R10.Esc后焦点恢复(非BODY)", focus_after in ("BUTTON", "A", "INPUT") , f"(实际 {focus_after})")

        # ============ R4：键盘搜索 Enter 跳转不闪退 ============
        note("== R4 键盘搜索 ==")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(400)
        check("R4.Ctrl+K打开搜索", page.locator(".search-modal").count() == 1)
        page.keyboard.type("lab.example.com", delay=20)
        page.wait_for_timeout(300)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(100)
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        drawer_open = page.locator(".drawer").count()
        search_gone = page.locator(".search-modal").count() == 0
        note(f"  after Enter: drawer={drawer_open}, search_closed={search_gone}")
        check("R4.Enter跳转抽屉保持打开", drawer_open == 1)
        check("R4.搜索框已关闭", search_gone)
        focus_in_drawer = page.evaluate(
            "(() => { const d=document.querySelector('.drawer'); return d ? d.contains(document.activeElement) : false })()"
        )
        check("R4.焦点在抽屉内", focus_in_drawer)
        shoot(page, "R4-enter-jump")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ============ R1：cloud 主键唯一 ============
        note("== R1 重复主键 ==")
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(300)
        # 服务资产页签计数
        tabs_txt = page.locator(".tabs").inner_text()
        note(f"  tabs: {tabs_txt.replace(chr(10),' | ')}")
        page.locator("input[aria-label='搜索资产']").fill("cloud.example.com")
        page.wait_for_timeout(300)
        rows = page.locator("table.data tbody tr")
        row_count = rows.count()
        note(f"  cloud rows: {row_count}")
        check("R1.cloud搜索仅1行", row_count == 1, f"(实际 {row_count})")
        # 点击该行，抽屉选用地址应为 .21 且展示备用地址 .22
        rows.first.click()
        page.wait_for_timeout(400)
        body = page.locator(".drawer .drawer-body").inner_text()
        check("R1.抽屉选用地址=.21", "198.51.100.21" in body)
        check("R1.抽屉展示备用地址.22", "198.51.100.22" in body and "其余解析地址" in body)
        shoot(page, "R1-cloud-single")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # 服务资产页签计数 = 概览可信资产数（15）
        page.locator("input[aria-label='搜索资产']").fill("")
        page.wait_for_timeout(200)
        tab_txt = page.locator(".tabs button", has_text="服务资产").inner_text()
        note(f"  服务资产 tab: {tab_txt}")
        check("R1.服务资产页签=15", "15" in tab_txt, f"(实际 {tab_txt})")

        # 导出 CSV 主键无重复
        with page.expect_download() as dl_info:
            page.get_by_role("button", name="导出当前结果 CSV").click()
        dl = dl_info.value
        csv_path = SHOTS / "export-assets.csv"
        dl.save_as(str(csv_path))
        csv_text = Path(csv_path).read_text(encoding="utf-8-sig")
        rdr = list(csvmod.reader(io.StringIO(csv_text)))
        keys = [f"{r[1]}|{r[2]}|{r[3]}" for r in rdr[1:] if len(r) >= 4]
        dups = [k for k in set(keys) if keys.count(k) > 1]
        note(f"  csv rows={len(keys)}, dup keys={dups}")
        check("R1.导出CSV主键无重复", len(dups) == 0, f"(重复 {dups})")

        # ============ R5：IP/域名页签隔离边界 ============
        note("== R5 隔离边界 ==")
        page.locator(".tabs button", has_text="IP").click()
        page.wait_for_timeout(300)
        ip_txt = page.locator(".table-wrap").inner_text()
        check("R5.IP页签无192.0.2.200", "192.0.2.200" not in ip_txt)
        check("R5.IP页签无198.51.100.50", "198.51.100.50" not in ip_txt)
        shoot(page, "R5-ip-tab")
        # 域名页签
        page.locator(".tabs button", has_text="域名").click()
        page.wait_for_timeout(300)
        _dom_txt = page.locator(".table-wrap").inner_text()
        # shop.example.org D+ 不可点击打开（点击应无抽屉）
        page.locator("table.data tbody tr", has_text="shop.example.org").click()
        page.wait_for_timeout(400)
        check("R5.点击D+域名不开抽屉", page.locator(".drawer").count() == 0)
        # iot.example.com 点击 → 进入筛选后的资产列表（有可见结果）
        page.locator("table.data tbody tr", has_text="iot.example.com").click()
        page.wait_for_timeout(400)
        # 应切到服务资产页签且 q=iot.example.com
        active_tab = page.locator(".tabs button.active").inner_text()
        search_val = page.locator("input[aria-label='搜索资产']").input_value()
        note(f"  after iot click: active_tab={active_tab!r}, q={search_val!r}")
        check("R5.点击iot进入筛选列表", "服务资产" in active_tab and "iot.example.com" in search_val)
        iot_rows = page.locator("table.data tbody tr").count()
        check("R5.iot筛选有可见结果", iot_rows >= 1, f"(行数 {iot_rows})")
        shoot(page, "R5-domain-list")

        # ============ R9：筛选上下文跨视图保留 ============
        note("== R9 筛选保留 ==")
        # 先回到服务资产页签，设置组合筛选
        page.locator("input[aria-label='搜索资产']").fill("")
        page.locator("select[aria-label='按公司筛选']").select_option(label="澄川云")
        page.locator("select[aria-label='按来源筛选']").select_option(label="FOFA")
        page.wait_for_timeout(300)
        # 切到关系图谱再返回
        page.locator(".sidebar .nav-item", has_text="关系图谱").click()
        page.wait_for_timeout(400)
        page.locator(".sidebar .nav-item", has_text="资产探索").click()
        page.wait_for_timeout(300)
        f_company = page.locator("select[aria-label='按公司筛选']").input_value()
        f_source = page.locator("select[aria-label='按来源筛选']").input_value()
        cnt = page.locator(".count-note").inner_text()
        note(f"  after round-trip: fCompany={f_company}, fSource={f_source}, count={cnt}")
        check("R9.公司筛选保留", f_company != "")
        check("R9.来源筛选保留", f_source == "FOFA")
        # 清空筛选便于后续
        page.get_by_role("button", name="清空筛选").click()
        page.wait_for_timeout(200)

        # ============ R8：可信口径（单来源C与无归属不计入） ============
        note("== R8 可信口径 ==")
        # 服务资产页签不应包含 192.0.2.10（无归属 502，已降 D）
        page.locator("input[aria-label='搜索资产']").fill("192.0.2.10")
        page.wait_for_timeout(300)
        rows8081 = page.locator("table.data tbody tr").count()
        # 可能显示空态行（colSpan），判断文本
        body_txt = page.locator("table.data tbody").inner_text()
        check("R8.无归属192.0.2.10不入可信", "8081" not in body_txt or "暂无资产数据" in body_txt, f"(rows {rows8081})")
        page.locator("input[aria-label='搜索资产']").fill("")
        page.wait_for_timeout(200)
        # 单来源 C（iot:5683 仅 Quake）不应出现在可信
        page.locator("input[aria-label='搜索资产']").fill("5683")
        page.wait_for_timeout(300)
        body_txt2 = page.locator("table.data tbody").inner_text()
        check("R8.单来源C(5683)不入可信", "5683" not in body_txt2 or "暂无资产数据" in body_txt2)
        page.locator("input[aria-label='搜索资产']").fill("")
        page.wait_for_timeout(200)

        # ============ R2：来源页能力 ============
        note("== R2 来源页 ==")
        page.locator(".sidebar .nav-item", has_text="数据来源").click()
        page.wait_for_timeout(300)
        src_txt = page.locator("main").inner_text()
        cards = page.locator("main .grid.cols-3 .panel")
        titles = [t.strip() for t in cards.locator("h3").all_inner_texts()]
        texts = cards.all_inner_texts()
        by_title = dict(zip(titles, texts))
        note(f"  卡片标题({len(titles)}): {titles}")
        # 卡片集合须与 dataset 的「6 家引擎 + 16 个采集工具/运行时依赖」一致
        expected_titles = {
            "FOFA", "Quake", "Hunter", "ZoomEye", "Shodan", "Censys",
            "subfinder（被动子域）", "OneForAll（子域）", "dnsx / dig（DNS）",
            "nmap（端口扫描）", "naabu（端口发现）", "a_scan（端口发现）",
            "httpx（Windows · Web 探测）", "httpx（WSL · 隔离 broker）",
            "katana（爬取 · JS 端点）", "ffuf（路径枚举）",
            "Playwright（Windows · 截图）", "gowitness（截图 · 隔离 broker）",
            "nuclei（模板核查）", "wafw00f（WAF 指纹）",
            "Chrome（gowitness 运行时依赖）", "SecLists（字典输入）",
        }
        check("R2.来源卡=22 且标题集合一致", len(titles) == 22 and set(titles) == expected_titles,
              f"(实际 {len(titles)}，缺 {sorted(expected_titles - set(titles))}，多 {sorted(set(titles) - expected_titles)})")
        # 旧的「未接入主流程」类表述必须已清零（Session 010 工具版本矩阵：这些工具均已接入）
        stale = [m for m in ("未接入主流程", "已安装，未接入", "WSL 完整接入", "端口扫描由 nmap 承担",
                             "尚待每浏览器请求的范围控制", "WSL 完整接入仍待实现") if m in src_txt]
        check("R2.无过期「未接入」表述", not stale, f"(残留 {stale})")
        # 徽章语义：integrated=已接入流水线（含可选引擎），inMainFlow 单独以「默认调度」呈现
        badge_texts = page.locator("main .grid.cols-3 .panel .badge").all_inner_texts()
        badges = [t.strip() for t in badge_texts]
        default_run = [t for t in badges if t == "默认调度"]
        integrated = [t for t in badges if t == "已接入流水线"]
        runtime_dep = [t for t in badges if t == "运行时依赖"]
        no_cred = [t for t in badges if t == "未配置凭据"]
        note(f"  徽章统计: 默认调度={len(default_run)}, 已接入流水线={len(integrated)}, "
             f"运行时依赖={len(runtime_dep)}, 未配置凭据={len(no_cred)}, 全部={sorted(set(badges))}")
        # 默认调度 = FOFA/Quake/subfinder/OneForAll/dnsx/nmap/httpx(Windows)/Playwright
        check("R2.默认调度徽章=8", len(default_run) == 8, f"(实际 {len(default_run)})")
        # 已接入流水线 = 六家中 FOFA/Quake + 14 个已接入工具（含可选引擎）
        check("R2.已接入流水线徽章=16", len(integrated) == 16, f"(实际 {len(integrated)})")
        check("R2.运行时依赖徽章=2(Chrome/SecLists)", len(runtime_dep) == 2, f"(实际 {len(runtime_dep)})")
        # 仅 FOFA 已配置凭据：其余五家标「未配置凭据」
        check("R2.未配置凭据徽章=5", len(no_cred) == 5, f"(实际 {len(no_cred)})")
        check("R2.FOFA卡不再标未配置凭据", "未配置凭据" not in by_title["FOFA"] and "受控被动试点" in by_title["FOFA"])
        # 无「实网已验证」徽章：真实账户泛化验收仍未执行
        check("R2.无实网已验证徽章", "实网已验证" not in badges)
        # 可选引擎确实以「已接入」而非「未接入」呈现，且写明谁承担该阶段
        for card, needle in (
            ("naabu（端口发现）", "nmap 确认服务"),
            ("httpx（WSL · 隔离 broker）", "隔离 broker"),
            ("katana（爬取 · JS 端点）", "-jc 默认开启"),
            ("ffuf（路径枚举）", "随机基线"),
            ("gowitness（截图 · 隔离 broker）", "由默认引擎 Playwright 承担"),
            ("nuclei（模板核查）", "待复核线索"),
            ("wafw00f（WAF 指纹）", "waf_fingerprint"),
        ):
            body = by_title[card]
            check(f"R2.{card}已接入且写明边界", "已接入流水线" in body and needle in body)
        # dnsx 卡不再声称可信解析路径待解决，改为已实施的可选 DoH
        check("R2.dnsx卡写明已实施 DoH", "DoH" in by_title["dnsx / dig（DNS）"] and "仍被劫持" in by_title["dnsx / dig（DNS）"])
        shoot(page, "R2-sources")

        # ============ R6：任务状态三处一致 ============
        note("== R6 任务状态 ==")
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        # 每个 run_id 仅一张卡片（无重复的 RUN-20261009-01）
        card_ids = page.locator(".grid.cols-3 .lead-item .mono").all_inner_texts()
        note(f"  task cards: {card_ids}")
        dup_ids = [c for c in set(card_ids) if card_ids.count(c) > 1]
        check("R6.列表无重复run卡片", len(dup_ids) == 0, f"(重复 {dup_ids})")
        # 打开 RUN-20261009-01：partial-failed，阶段流程应含 1 项失败标示
        page.locator(".grid.cols-3 .lead-item", has_text="RUN-20261009-01").click()
        page.wait_for_timeout(400)
        pipeline_txt = page.locator(".pipeline").inner_text()
        check("R6.阶段流程含失败标示", "✕" in pipeline_txt)
        shoot(page, "R6-task-stages")
        # 推进到 8/8 后无悬挂子任务
        # 先重试失败的截图子任务（R6 验收：重试后 +3）
        retry_btn = page.get_by_role("button", name="重试（模拟）")
        if retry_btn.count() > 0:
            # 读取重试前结果数
            retry_btn.first.click()
            page.wait_for_timeout(400)
            note("  retried failed subtask")
        # 连续推进直到无「模拟推进一阶段」按钮
        for _ in range(10):
            adv = page.get_by_role("button", name="模拟推进一阶段")
            if adv.count() == 0:
                break
            adv.first.click()
            page.wait_for_timeout(300)
        # report 子任务行：状态徽章应为「完成」，不再停留「等待」
        report_row = page.locator("table.data tbody tr", has_text="report")
        report_txt = report_row.inner_text() if report_row.count() else ""
        note(f"  report row after advance: {report_txt.replace(chr(10),' | ')[:160]}")
        check("R6.推进后report子任务已完成", "完成" in report_txt and "等待" not in report_txt.split("完成")[0])
        detail_txt = page.locator("main").inner_text()
        check("R6.推进后8/8完成", "已完成" in detail_txt)
        shoot(page, "R6-task-done")
        # 返回列表仍每个 run 一张卡
        page.get_by_role("button", name="返回任务列表").click()
        page.wait_for_timeout(300)
        card_ids2 = page.locator(".grid.cols-3 .lead-item .mono").all_inner_texts()
        dup2 = [c for c in set(card_ids2) if card_ids2.count(c) > 1]
        check("R6.推进后列表仍无重复卡", len(dup2) == 0, f"(cards {card_ids2})")

        # ============ 链路 B：新建演示任务 → 重试 → 持久化 → 重置 ============
        note("== 链路 B ==")
        page.get_by_role("button", name="新建调查（演示）").click()
        page.wait_for_timeout(400)
        check("B.向导打开", page.locator(".modal").count() == 1)
        # R10: 向导 Esc 可关闭
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("B.向导Esc关闭", page.locator(".modal").count() == 0)
        # 重新打开走完四步
        page.get_by_role("button", name="新建调查（演示）").click()
        page.wait_for_timeout(400)
        for _ in range(3):
            page.get_by_role("button", name="下一步").click()
            page.wait_for_timeout(250)
        page.get_by_role("button", name="创建演示任务").click()
        page.wait_for_timeout(500)
        demo_txt = page.locator("main").inner_text()
        check("B.演示任务已创建", "DEMO-" in demo_txt)
        demo_id = page.evaluate("document.querySelector('.mono.hint')?.textContent || ''")
        note(f"  demo id: {demo_id}")
        shoot(page, "B-demo-task")
        # 刷新持久化
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        page.locator(".sidebar .nav-item", has_text="调查任务").click()
        page.wait_for_timeout(300)
        persist_txt = page.locator("main").inner_text()
        check("B.刷新后演示任务持久化", "DEMO-" in persist_txt)
        # 重置演示
        page.locator(".sidebar .nav-item", has_text="证据复核").click()
        page.wait_for_timeout(300)
        page.on("dialog", lambda d: d.accept())
        page.get_by_role("button", name="重置演示").click()
        page.wait_for_timeout(400)
        ls = page.evaluate("localStorage.getItem('asm-workbench-local-v1')")
        note(f"  localStorage after reset: {ls}")
        page.locator(".sidebar .nav-item", has_text="项目概览").click()
        page.wait_for_timeout(300)
        v = dict(zip(
            [lbl.strip() for lbl in page.locator(".stat-card .label").all_inner_texts()],
            page.locator(".stat-card .value").all_inner_texts()
        ))
        note(f"  stats after reset: {v}")
        check("B.重置后可信资产=15", v.get("可信资产") == "15")
        check("B.重置后待核对=12", v.get("待核对线索") == "12")

        # ============ R1/R3：报告中心总表与口径 ============
        note("== 报告中心 ==")
        page.locator(".sidebar .nav-item", has_text="报告中心").click()
        page.wait_for_timeout(300)
        summary_txt = page.locator("main").inner_text()
        check("R3.汇报视图新增=2且无约字凑数", "新增可信资产" in summary_txt and "约" not in summary_txt.split("较上轮变化")[1][:60] if "较上轮变化" in summary_txt else False)
        # 工程明细 → 总表
        page.locator(".tabs button", has_text="工程明细").click()
        page.wait_for_timeout(300)
        master_txt = page.locator(".table-wrap").inner_text()
        note(f"  master rows hint: {page.locator('.report-table-note').inner_text()}")
        check("R1.总表15行", "共 15 行" in page.locator(".report-table-note").inner_text())
        # cloud 行截图列保留 .21 的已采集截图（demo-shot-cloud.png），非「未采集」
        cloud_row = page.locator("table.data tbody tr", has_text="cloud.example.com")
        cloud_txt = cloud_row.inner_text() if cloud_row.count() else ""
        note(f"  cloud master row: {cloud_txt.replace(chr(10),' | ')[:120]}")
        check("R1.总表cloud行截图=demo-shot-cloud.png", "demo-shot-cloud.png" in cloud_txt)
        check("R1.总表cloud仅1行", cloud_row.count() == 1)
        check("R8.总表无D+(shop/198.51.100.50)", "shop.example.org" not in master_txt and "198.51.100.50" not in master_txt and "192.0.2.10" not in master_txt)
        shoot(page, "R-report-master")

        # ============ R7：畸形 localStorage 不白屏 ============
        note("== R7 容错 ==")
        page.evaluate("""() => {
          localStorage.setItem('asm-workbench-local-v1', JSON.stringify({demoTasks:[{id:'X',name:'x'}]}));
        }""")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(500)
        root_html_len = page.evaluate("document.getElementById('root')?.innerHTML.length || 0")
        check("R7.坏数据不白屏", root_html_len > 500, f"(root len {root_html_len})")
        # 页面应可渲染且能点重置（或坏任务被丢弃）
        body_txt = page.locator("body").inner_text()
        check("R7.页面可交互渲染", "项目概览" in body_txt or "重置" in body_txt)
        # 恢复：清掉坏键
        page.evaluate("localStorage.removeItem('asm-workbench-local-v1')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        # 非法 JSON
        page.evaluate("localStorage.setItem('asm-workbench-local-v1', '{not json')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        root_len2 = page.evaluate("document.getElementById('root')?.innerHTML.length || 0")
        check("R7.非法JSON可自愈", root_len2 > 500)
        page.evaluate("localStorage.removeItem('asm-workbench-local-v1')")
        page.reload(wait_until="networkidle")

        # ============ 汇总 ============
        note("\n==== 结果汇总 ====")
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        note(f"PASS {passed}/{total}")
        for k, v in results.items():
            if not v:
                note(f"  FAIL: {k}")
        note(f"page errors: {errors[:10]}")
        check("无页面JS错误", len([e for e in errors if "Warning" not in e]) == 0, f"({len(errors)})")

        (SHOTS / "verify-results.json").write_text(
            json.dumps({"passed": passed, "total": total, "results": results, "errors": errors}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        browser.close()
    srv.shutdown()
    return all(results.values())

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)

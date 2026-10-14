# -*- coding: utf-8 -*-
"""第二轮评审独立探针（GLM/Kimi 之外的补充验证）：
P1  V1 对比度实测：各视图采样元素 computed color × 有效背景，计算 WCAG 对比度
P2  V2 视口实测：1920/1280/390 三档，页面无横向溢出、栅格列数、抽屉宽度
P3  R6 初始态一致性：RUN-20261009-01 的阶段流程与子任务状态是否自洽（s8 vs st6）
P4  快照差分披露：oa.example.com|443 离开可信集是否在任何视图体现
P5  回归抽查：概览指标 15/14/12/2、来源页 FOFA 徽章、总表 15 行、390 抽屉适配、行 Enter 打开抽屉
仅本地 dist + 本地静态服务，无任何外部网络请求。产物写 ASM_PROBE_OUT（默认临时目录）。
"""
import json
import os
import sys
import tempfile
import threading
import http.server
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

ROOT = Path(r"D:\Desktop\asm\frontend\dist")
OUT = Path(os.environ.get("ASM_PROBE_OUT") or os.path.join(tempfile.gettempdir(), "asm-review2-probes"))
OUT.mkdir(parents=True, exist_ok=True)
PORT = 6293
BASE = f"http://127.0.0.1:{PORT}"

results = {}
log_lines = []


def note(m):
    log_lines.append(m)
    print(m, flush=True)


def record(k, v):
    results[k] = v
    note(f"  [probe] {k} = {json.dumps(v, ensure_ascii=False)[:500]}")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, *a):
        pass


def start_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


CONTRAST_JS = """
() => {
  function lum(r, g, b) {
    const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  function parse(c) {
    const m = c.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    if (!m) return null;
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  }
  function bgOf(el) {
    let e = el;
    while (e) {
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0.9) return c;
      e = e.parentElement;
    }
    return { r: 244, g: 246, b: 248, a: 1 };
  }
  const out = [];
  const sel = '.hint,.desc,.foot,.reason,.sub,.count-note,.report-table-note,.badge,td,th,.notice,dt,dd,.trail-node .k,.nav-item,.empty,.chip,.timeline .ts,.log-box,.stat-card .label,.stat-card .value,.lead-item .target,.lead-item .reason,button';
  document.querySelectorAll(sel).forEach((el) => {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    if (parseFloat(cs.opacity) < 0.99) return;
    const txt = (el.textContent || '').trim();
    if (!txt) return;
    const fg = parse(cs.color);
    if (!fg) return;
    const bg = bgOf(el);
    const L1 = lum(fg.r, fg.g, fg.b), L2 = lum(bg.r, bg.g, bg.b);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const need = large ? 3 : 4.5;
    if (ratio < need) {
      out.push({
        text: txt.slice(0, 36),
        cls: String(el.className || el.tagName).slice(0, 50),
        fg: cs.color,
        bg: 'rgb(' + bg.r + ',' + bg.g + ',' + bg.b + ')',
        px: size, weight,
        ratio: +ratio.toFixed(2), need,
      });
    }
  });
  return { failing: out.length, samples: out.slice(0, 80) };
}
"""

LAYOUT_JS = """
() => {
  const doc = document.documentElement;
  const g = (sel) => {
    const n = document.querySelector(sel);
    return n ? getComputedStyle(n).gridTemplateColumns.split(' ').filter((x) => x.length).length : null;
  };
  const rect = (sel) => {
    const n = document.querySelector(sel);
    return n ? +n.getBoundingClientRect().width.toFixed(0) : null;
  };
  return {
    scrollW: doc.scrollWidth, clientW: doc.clientWidth,
    cols4: g('.grid.cols-4'), cols3: g('.grid.cols-3'), cols2: g('.grid.cols-2'),
    sidebarW: rect('.sidebar'), mainW: rect('main.main'),
    statW: rect('.stat-card'), drawerW: rect('.drawer'),
    tableOverflow: (() => {
      const t = document.querySelector('.table-wrap');
      return t ? { scroll: t.scrollWidth, client: t.clientWidth } : null;
    })(),
  };
}
"""

VIEWS = [
    ("overview", "项目概览"),
    ("assets", "资产探索"),
    ("tasks", "调查任务"),
    ("review", "证据复核"),
    ("graph", "关系图谱"),
    ("sources", "数据来源"),
    ("reports", "报告中心"),
]


def main():
    srv = start_server()
    note(f"server on {BASE}")
    errors_total = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---------- P1: 对比度（1440 基准视口，7 视图） ----------
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
            page = ctx.new_page()
            page.goto(BASE, wait_until="networkidle")
            page.wait_for_timeout(300)
            contrast = {}
            for view, label in VIEWS:
                page.locator(".sidebar .nav-item", has_text=label).click()
                page.wait_for_timeout(250)
                contrast[view] = page.evaluate(CONTRAST_JS)
            record("P1.对比度不足元素数(按视图)", {k: v["failing"] for k, v in contrast.items()})
            # 聚合最常见的失败组合（fg×bg×px）
            agg = {}
            for v in contrast.values():
                for s in v["samples"]:
                    key = f"{s['fg']} on {s['bg']} @{s['px']}px"
                    agg[key] = agg.get(key, 0) + 1
            top = sorted(agg.items(), key=lambda kv: -kv[1])[:12]
            record("P1.对比度失败组合TOP12", dict(top))
            record("P1.样本明细前25", contrast["overview"]["samples"][:25])
            ctx.close()
        except Exception as exc:
            record("P1.异常", type(exc).__name__ + ": " + str(exc)[:200])

        # ---------- P2: 视口 1920 / 1280 / 390 ----------
        try:
            layout = {}
            for w, h in [(1920, 1080), (1280, 800), (390, 844)]:
                ctx = browser.new_context(viewport={"width": w, "height": h}, locale="zh-CN")
                page = ctx.new_page()
                page.goto(BASE, wait_until="networkidle")
                page.wait_for_timeout(250)
                lay = page.evaluate(LAYOUT_JS)
                # 390：打开抽屉看适配
                if w == 390:
                    page.locator(".sidebar .nav-item", has_text="资产探索").click()
                    page.wait_for_timeout(250)
                    page.locator("table.data tbody tr").first.click()
                    page.wait_for_timeout(400)
                    lay["drawerW_open"] = page.evaluate(
                        "document.querySelector('.drawer') ? document.querySelector('.drawer').getBoundingClientRect().width : null")
                if w == 1920:
                    page.locator(".sidebar .nav-item", has_text="资产探索").click()
                    page.wait_for_timeout(250)
                    page.locator("table.data tbody tr").first.click()
                    page.wait_for_timeout(400)
                    lay["drawerW_open"] = page.evaluate(
                        "document.querySelector('.drawer') ? document.querySelector('.drawer').getBoundingClientRect().width : null")
                layout[f"{w}x{h}"] = lay
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                ctx.close()
            record("P2.布局测量", layout)
            record("P2.横向溢出判定", {k: ("溢出" if v["scrollW"] > v["clientW"] else "无溢出") for k, v in layout.items()})
        except Exception as exc:
            record("P2.异常", type(exc).__name__ + ": " + str(exc)[:200])

        # ---------- P3: R6 初始态（RUN-20261009-01 阶段 vs 子任务） ----------
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
            page = ctx.new_page()
            page.goto(BASE, wait_until="networkidle")
            page.locator(".sidebar .nav-item", has_text="调查任务").click()
            page.wait_for_timeout(300)
            page.locator(".grid.cols-3 .lead-item", has_text="RUN-20261009-01").click()
            page.wait_for_timeout(400)
            state = page.evaluate("""
() => {
  const steps = [...document.querySelectorAll('.pipeline .step .node')].map(n => n.textContent.trim());
  const subs = [...document.querySelectorAll('table.data tbody tr')].map(r => r.textContent.trim().replace(/\\s+/g, ' '));
  return { steps, subs };
}
""")
            record("P3.R6初始阶段流程", state["steps"])
            record("P3.R6初始子任务", state["subs"])
            s8 = [s for s in state["steps"] if "报告" in s]
            record("P3.判定", {
                "s8显示": s8,
                "s8是否running(●)": any(s.startswith("●") for s in s8),
                "st6是否等待": any("report" in s and "等待" in s for s in state["subs"]),
            })
            ctx.close()
        except Exception as exc:
            record("P3.异常", type(exc).__name__ + ": " + str(exc)[:200])

        # ---------- P4: 快照移除披露 ----------
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
            page = ctx.new_page()
            page.goto(BASE, wait_until="networkidle")
            page.locator(".sidebar .nav-item", has_text="项目概览").click()
            page.wait_for_timeout(300)
            ov_txt = page.locator("main").inner_text()
            page.locator(".sidebar .nav-item", has_text="报告中心").click()
            page.wait_for_timeout(300)
            rp_txt = page.locator("main").inner_text()
            record("P4.概览提及oa移除", "oa.example.com" in ov_txt)
            record("P4.报告提及oa移除", "oa.example.com" in rp_txt)
            record("P4.概览含离开可信集字样", ("离开" in ov_txt) or ("移出" in ov_txt) or ("降级" in ov_txt))
            ctx.close()
        except Exception as exc:
            record("P4.异常", type(exc).__name__ + ": " + str(exc)[:200])

        # ---------- P5: 回归抽查 ----------
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("console", lambda m: errs.append(f"console.{m.type}:{m.text}") if m.type == "error" else None)
            page.goto(BASE, wait_until="networkidle")
            page.wait_for_timeout(300)
            stats = dict(zip(
                [lbl.strip() for lbl in page.locator(".stat-card .label").all_inner_texts()],
                page.locator(".stat-card .value").all_inner_texts()))
            record("P5.概览指标", stats)
            record("P5.指标回归", {
                "可信15": stats.get("可信资产") == "15",
                "域名14": stats.get("已收集域名") == "14",
                "待核对12": stats.get("待核对线索") == "12",
                "新增2": stats.get("本轮新增可信资产") == "2",
            })
            # 来源页 FOFA 徽章
            page.locator(".sidebar .nav-item", has_text="数据来源").click()
            page.wait_for_timeout(250)
            fofa_card = page.locator(".panel", has_text="FOFA").first
            record("P5.FOFA卡徽章", [b.strip() for b in fofa_card.locator(".badge").all_inner_texts()])
            # 总表 15 行 + cloud 单行
            page.locator(".sidebar .nav-item", has_text="报告中心").click()
            page.wait_for_timeout(250)
            page.locator(".tabs button", has_text="工程明细").click()
            page.wait_for_timeout(250)
            page.locator(".filter-bar .btn", has_text="总表").click()
            page.wait_for_timeout(250)
            note_txt = page.locator(".report-table-note").inner_text()
            cloud_rows = page.locator("table.data tbody tr", has_text="cloud.example.com").count()
            record("P5.总表行数注", note_txt.strip()[:40])
            record("P5.总表cloud行数", cloud_rows)
            # 资产行键盘 Enter 打开抽屉
            page.locator(".sidebar .nav-item", has_text="资产探索").click()
            page.wait_for_timeout(250)
            page.locator("table.data tbody tr").first.focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            record("P5.行Enter打开抽屉", page.locator(".drawer").count() == 1)
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
            errors_total.extend(errs)
            record("P5.页面JS错误数", len(errs))
            ctx.close()
        except Exception as exc:
            record("P5.异常", type(exc).__name__ + ": " + str(exc)[:200])

        browser.close()
    srv.shutdown()

    (OUT / "probe-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "probe-log.txt").write_text("\n".join(log_lines), encoding="utf-8")
    note(f"\nprobes done -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

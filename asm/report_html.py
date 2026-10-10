"""Standalone, offline HTML report with escaped evidence and embedded PNG screenshots."""
import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from html import escape


STYLE = """
:root{color-scheme:light;--ink:#183153;--muted:#596b80;--line:#dce5ee;--accent:#087f8c}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f6fa;color:var(--ink);
font:14px/1.55 'Segoe UI','Microsoft YaHei',Arial,sans-serif}a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}[hidden]{display:none!important}.wrap{max-width:1600px;margin:auto;padding:28px}
.hero{padding:28px 32px;background:#183153;border-radius:16px;color:white}.eyebrow{font-size:12px;
letter-spacing:2px;color:#b4dfe4}.hero h1{font-size:30px;line-height:1.3;margin:10px 0 12px}
.hero p{margin:6px 0;color:#dce5ee}.badge{display:inline-block;padding:5px 11px;border:1px solid #7594ad;
border-radius:99px;margin-top:12px;font-size:12px}.stats{display:grid;grid-template-columns:repeat(4,1fr);
gap:14px;margin:20px 0}.stat{background:white;border:1px solid var(--line);border-radius:12px;padding:16px 20px}
.stat strong{display:block;font-size:28px}.muted{color:var(--muted)}.toolbar{display:flex;flex-wrap:wrap;
gap:12px;align-items:center;padding:16px 0}.toolbar label{font-weight:600}.toolbar input{width:min(460px,100%);
padding:10px 14px;font:inherit;border:1px solid #9fb0c3;border-radius:8px;background:white}
nav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}nav a{background:white;border:1px solid var(--line);
border-radius:8px;padding:8px 12px}.section{background:white;border:1px solid var(--line);border-radius:12px;
margin:18px 0;overflow:hidden;scroll-margin-top:18px}.section-head{display:flex;flex-wrap:wrap;gap:10px;
align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--line)}
h2{font-size:19px;margin:0}.section-head span{font-size:12px;color:var(--muted)}.table-scroll{overflow:auto}
table{border-collapse:collapse;width:100%;min-width:820px}th{background:#eaf0f6;font-size:12px;
letter-spacing:.2px;text-align:left;white-space:nowrap}th,td{padding:11px 14px;border-bottom:1px solid #edf1f6;
vertical-align:top}td{white-space:pre-wrap;overflow-wrap:anywhere;max-width:420px}tbody tr:nth-child(even){background:#f8fafc}
tbody tr:hover{background:#edf7f8}.empty td{text-align:center;padding:30px;color:var(--muted)}
.image-link{white-space:nowrap}.gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;padding:20px}
.screenshot-card{border:1px solid var(--line);border-radius:10px;overflow:hidden;scroll-margin-top:20px}
.screenshot-card h3{font-size:14px;margin:0;padding:12px 16px;background:#edf2f7;overflow-wrap:anywhere}
.screenshot-card img{display:block;width:100%;height:auto;background:white}.image-note{padding:20px;color:var(--muted)}
footer{padding:18px 4px;color:var(--muted);font-size:12px}noscript{display:block;padding:10px 0;color:var(--muted)}
@media(max-width:760px){.wrap{padding:14px}.hero{padding:22px}.hero h1{font-size:23px}
.stats{grid-template-columns:repeat(2,1fr)}.gallery{grid-template-columns:1fr}}
@media print{body{background:white}.wrap{padding:0}.toolbar,nav{display:none}.section{break-inside:avoid}
.table-scroll{overflow:visible}table{min-width:0;font-size:9px}th,td{padding:5px}.gallery{grid-template-columns:1fr}}
"""

SCRIPT = """document.getElementById('search').addEventListener('input', function () {
  const query = this.value.trim().toLocaleLowerCase();
  document.querySelectorAll('section[data-sheet]').forEach(function (section) {
    const rows = section.querySelectorAll('tbody tr.data-row');
    let visible = 0;
    rows.forEach(function (row) {
      row.hidden = query !== '' && !row.textContent.toLocaleLowerCase().includes(query);
      if (!row.hidden) visible += 1;
    });
    section.querySelector('[data-visible-count]').textContent = visible;
    const empty = section.querySelector('tr.empty');
    empty.hidden = visible !== 0;
    empty.querySelector('td').textContent = query ? '没有匹配的记录' : '暂无记录';
  });
});"""


def html_text(value):
    return escape(str(value) if value is not None else "", quote=True)


def screenshot_data(rows, directory, issues):
    result = {}
    for row in rows["总表"]:
        number, relative = row[0], row[8]
        item = {"number": number, "label": f"{row[1]}:{row[2]}", "uri": "",
                "issue": issues.get(number, "截图文件缺失或不可读取")}
        if relative and re.fullmatch(r"screenshots/[1-9][0-9]*\.png", relative):
            try:
                data = (directory / relative).read_bytes()
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("Not PNG")
                item["uri"] = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            except (OSError, ValueError):
                item["issue"] = "截图文件无法作为 PNG 显示"
        result[number] = item
    return result


def html_cell(header, value, images):
    if header in {"截图链接", "screenshot"}:
        match = re.fullmatch(r"screenshots/([1-9][0-9]*)\.png", str(value or ""))
        if match and int(match[1]) in images:
            item = images[int(match[1])]
            label = "查看首页截图" if item["uri"] else "查看截图状态"
            return f'<a class="image-link" href="#screenshot-{item["number"]}">{label}</a>'
        return '<span class="muted">无截图</span>'
    return html_text(value)


def write_html(headers, rows, path, *, screenshot_issues=None):
    images = screenshot_data(rows, path.parent, screenshot_issues or {})
    image_count = sum(bool(item["uri"]) for item in images.values())
    counts = {name: len(values) for name, values in rows.items()}
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    company = next((row[1] for row in rows["equity"] if row[1]), "未填写主体")
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode("ascii")
    policy = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
              f"script-src 'sha256-{script_hash}'; base-uri 'none'; form-action 'none'; connect-src 'none'")
    parts = ["<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">",
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             f'<meta http-equiv="Content-Security-Policy" content="{html_text(policy)}">',
             "<title>互联网暴露面资产报告</title>", f"<style>{STYLE}</style></head><body><main class=\"wrap\">",
             '<header class="hero"><div class="eyebrow">ATTACK SURFACE INVENTORY</div>',
             "<h1>互联网暴露面资产报告</h1>",
             f"<p>主体：{html_text(company)} · 生成时间：{stamp}（北京时间）</p>",
             "<p>资产归属、服务信息与待核对线索；置信度和候选项仍需结合原始证据确认。</p>",
             f'<span class="badge">离线可查看 · 已内嵌 {image_count} 张首页截图</span></header>',
             '<div class="stats">']
    for name, label in (("总表", "可信资产"), ("domains", "域名"), ("urls", "URL 记录"), ("todos", "待核对项")):
        parts.append(f'<div class="stat"><span class="muted">{label}</span><strong>{counts[name]}</strong></div>')
    parts += ['</div><div class="toolbar"><label for="search">搜索全部表格</label>',
              '<input id="search" type="search" placeholder="资产、域名、标题、来源或证据" autocomplete="off">',
              '<span class="muted">输入后筛选记录；截图证据始终保留。</span></div>',
              "<noscript>浏览器未启用 JavaScript，全部表格与内嵌截图仍可查看。</noscript><nav aria-label=\"报告导航\">"]
    for index, name in enumerate(headers):
        parts.append(f'<a href="#sheet-{index}">{html_text(name)} · {counts[name]}</a>')
    parts += [f'<a href="#screenshots">首页截图 · {image_count}</a></nav>']
    for index, (name, fields) in enumerate(headers.items()):
        parts += [f'<section class="section" id="sheet-{index}" data-sheet="{html_text(name)}">',
                  '<div class="section-head">', f"<h2>{html_text(name)}</h2>",
                  f'<span>显示 <b data-visible-count>{counts[name]}</b> / {counts[name]} 条</span></div>',
                  f'<div class="table-scroll"><table aria-label="{html_text(name)}"><thead><tr>']
        parts += [f'<th scope="col">{html_text(field)}</th>' for field in fields]
        parts += ["</tr></thead><tbody>"]
        for values in rows[name]:
            parts.append('<tr class="data-row">')
            parts += [f"<td>{html_cell(field, value, images)}</td>" for field, value in zip(fields, values)]
            parts.append("</tr>")
        hidden = " hidden" if rows[name] else ""
        parts += [f'<tr class="empty"{hidden}><td colspan="{len(fields)}">暂无记录</td></tr>',
                  "</tbody></table></div></section>"]
    parts += ['<section class="section" id="screenshots"><div class="section-head">',
              "<h2>首页截图与状态</h2>", f"<span>{image_count} 张图片 / {len(images)} 条资产</span></div>",
              '<div class="gallery">']
    for number, item in images.items():
        parts += [f'<article class="screenshot-card" id="screenshot-{number}">',
                  f'<h3>#{number} · {html_text(item["label"])}</h3>']
        if item["uri"]:
            parts.append(f'<img src="{item["uri"]}" alt="{html_text(item["label"])} 首页截图" loading="lazy">')
        else:
            parts.append(f'<div class="image-note">{html_text(item["issue"])}</div>')
        parts.append("</article>")
    if not images:
        parts.append('<p class="muted">暂无资产；本报告未采集首页截图。</p>')
    parts += ["</div></section><footer>本文件包含全部八张表及可读取的 PNG 截图，不依赖网络或外部图片文件。",
              "未采集、缺失或不可读取的截图无法由报告恢复；状态已列出。待核对项不代表已确认漏洞。</footer>",
              f"</main><script>{SCRIPT}</script></body></html>"]
    path.write_text("\n".join(parts), encoding="utf-8")

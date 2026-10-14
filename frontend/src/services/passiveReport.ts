// ============================================================
// 被动试点（tk.cn）独立 HTML 报告导出：模板 + 本地下载。
// 设计目标：单文件、离线可开、内嵌 2 张证据截图、零外部请求。
// ============================================================
import {
  TKCN_META,
  TKCN_QUERIES,
  TKCN_CANDIDATES,
  TKCN_NEIGHBORS,
  TKCN_DNS,
  TKCN_SUBDOMAINS,
  TKCN_HIGHLIGHTS,
  TKCN_RESOLVERS,
  TKCN_SHOT1,
  TKCN_SHOT2,
  type PilotCandidate,
  type PilotNeighbor,
  type PilotQuery,
  type PilotDnsObservation,
} from "../data/tkcnEvidence";

function esc(v: unknown): string {
  return String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

function download(filename: string, mime: string, text: string): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function queryRows(queries: PilotQuery[]): string {
  return queries
    .map(
      (q) => `<tr>
      <td><code>${esc(q.tag)}</code></td>
      <td><code>${esc(q.query)}</code></td>
      <td>${esc(q.round)}</td>
      <td>${q.ok ? esc(q.total ?? 0) : "—"}</td>
      <td>${q.ok ? q.returned : 0}</td>
      <td>${esc(q.confidence)}</td>
      <td>${esc(q.fpoint ?? 0)}</td>
      <td>${q.ok ? '<span class="ok">成功</span>' : `<span class="bad">${esc(q.error || "失败")}</span>`}</td>
    </tr>`,
    )
    .join("");
}

function candidateRows(candidates: PilotCandidate[]): string {
  return candidates
    .map((c) => {
      const dns = c.dns.cnameChain.length
        ? `CDN：${esc(c.dns.cnameChain.join(" → "))}`
        : c.dns.resolved
          ? `解析 ${c.dns.ips.length} 个 IP`
          : "DNS 无 A 记录";
      return `<tr>
      <td class="mono">${esc(c.host)}:${c.port}</td>
      <td class="mono">${esc(c.ip)}</td>
      <td>${esc(c.title || c.product || "—")}</td>
      <td>${esc(c.city || "—")}</td>
      <td>${dns}${c.dns.inconsistent ? '<span class="warn"> 多上游不一致</span>' : ""}</td>
      <td>${c.labels.map((l) => `<span class="label">${esc(l)}</span>`).join(" ") || "—"}</td>
    </tr>`;
    })
    .join("");
}

function neighborRows(neighbors: PilotNeighbor[]): string {
  const kindText: Record<PilotNeighbor["kind"], string> = {
    vendor: "供应商",
    anomaly: "疑似仿冒",
    group: "集团邻域",
    ip: "邻域/IP",
    noise: "噪声",
  };
  return neighbors
    .filter((n) => n.kind !== "noise")
    .map(
      (n) => `<tr>
      <td class="mono">${esc(n.host)}:${n.port}</td>
      <td class="mono">${esc(n.ip)}</td>
      <td>${kindText[n.kind]}</td>
      <td>${esc(n.title || "—")}</td>
      <td>${esc(n.note)}</td>
    </tr>`,
    )
    .join("");
}

function dnsRows(dns: PilotDnsObservation[]): string {
  return dns
    .map((d) => {
      const resolved = d.upstreams.some((u) => u.answers.length > 0);
      const inconsistent =
        new Set(d.upstreams.filter((u) => u.answers.length).map((u) => u.answers.slice().sort().join(","))).size > 1;
      const summary = d.upstreams
        .map((u) => `${esc(u.upstream)}→${u.answers.length ? esc(u.answers.join(",")) : u.cnameChain.length ? "CNAME" : esc(u.status)}`)
        .join("<br>");
      return `<tr class="${resolved ? "" : "muted"}">
      <td class="mono">${esc(d.domain)}</td>
      <td>${resolved ? (d.upstreams.some((u) => u.cnameChain.length) ? "CDN/CNAME" : "直连") : "无 A 记录"}${inconsistent ? ' <span class="warn">多上游不一致</span>' : ""}</td>
      <td class="small">${summary}</td>
    </tr>`;
    })
    .join("");
}

export function buildPassivePilotReportHtml(): string {
  const c = TKCN_META.counts;
  // 重点发现全部来自生成数据（TKCN_HIGHLIGHTS），模板不硬编码任何真实资产字符串
  const highlights = TKCN_HIGHLIGHTS;
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tk.cn 纯被动信息收集报告（试点轮·正常流程）</title>
<style>
  :root{color-scheme:light;--ink:#172535;--ink3:#5a6e7e;--line:#e3e8ee;--accent:#0f6673}
  *{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:var(--ink);
  font:14px/1.65 "PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif}
  .wrap{max-width:1240px;margin:0 auto;padding:28px 22px 60px}
  .hero{background:#12202e;color:#e8eef4;border-radius:12px;padding:26px 30px;margin-bottom:18px}
  .hero h1{margin:0 0 6px;font-size:22px}.hero .sub{color:#9fb3c4;font-size:13px}
  .badge{display:inline-block;background:#17324a;color:#8fd3e0;border-radius:999px;padding:2px 11px;font-size:12px;margin:2px 6px 0 0}
  .card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0}
  .card h2{margin:0 0 10px;font-size:16.5px}
  .notice{border-left:4px solid #96601a;background:#fdf3e0;border-radius:8px;padding:10px 14px;font-size:13px;margin:12px 0}
  .notice.green{border-color:#276749;background:#e8f5ee}
  .notice.red{border-color:#c0392b;background:#fdeceb}
  table{border-collapse:collapse;width:100%;font-size:12.8px}
  th{background:#eef2f6;text-align:left;padding:7px 9px;border:1px solid var(--line)}
  td{padding:6px 9px;border:1px solid var(--line);vertical-align:top}
  td.mono{font-family:Consolas,"Cascadia Code",monospace;color:var(--accent);white-space:nowrap}
  td.small{font-size:11.5px;font-family:Consolas,monospace}
  .kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
  .kpi .item{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:10px 14px}
  .kpi .n{font-size:24px;font-weight:700;color:var(--accent)}.kpi .l{font-size:12px;color:var(--ink3)}
  img.shot{width:100%;border:1px solid var(--line);border-radius:8px;margin:8px 0 2px}
  .cap{font-size:12px;color:var(--ink3);margin-bottom:10px}
  .label{display:inline-block;background:#edf1f5;border-radius:6px;padding:0 6px;font-size:11.5px;margin:0 3px 0 0}
  .warn{color:#96601a;font-size:11.5px}.ok{color:#276749}.bad{color:#c0392b}
  ul{margin:6px 0;padding-left:22px}li{margin:3px 0}code{background:#eef2f6;border-radius:4px;padding:1px 5px;font-size:12.5px}
  footer{color:var(--ink3);font-size:12px;margin-top:22px;text-align:center}
  .muted{color:var(--ink3)}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
  <h1>tk.cn 纯被动信息收集报告 <span style="font-size:13px;color:#9fb3c4">（试点轮 · 正常流程 · 单源 FOFA + CT/被动DNS + 公共解析器观测）</span></h1>
  <div class="sub">目标：${esc(TKCN_META.org)}（${esc(TKCN_META.target)}） · 生成（UTC）：${esc(TKCN_META.stamp)} · 执行：暴露面收集框架 + 人工独立调用（profile=tkcn）</div>
  <div style="margin-top:10px">
    <span class="badge">零发包</span><span class="badge">仅第三方数据源</span><span class="badge">FOFA 限速 ≥20s</span>
    <span class="badge">当日 11 次 / 0 F 点</span><span class="badge">候选 · 未授权阶段</span>
  </div>
</div>

<div class="notice red"><b>边界声明（最重要）</b>：${esc(TKCN_META.boundary)}。
本报告全部结论均为候选线索（candidate_only），不构成对目标资产的确认；主动核实（端口/页面/证书明细）须在获得书面授权后进行。</div>

<div class="card">
  <h2>一、执行摘要</h2>
  <div class="kpi">
    <div class="item"><div class="n">${c.subdomains}</div><div class="l">发现子域（三源并集）</div></div>
    <div class="item"><div class="n">${c.candidates}</div><div class="l">候选资产（host+port）</div></div>
    <div class="item"><div class="n">${c.dnsResolved}</div><div class="l">DNS 解析（公共解析器）</div></div>
    <div class="item"><div class="n">${c.cdnCname}</div><div class="l">CDN/CNAME 链</div></div>
    <div class="item"><div class="n">${c.neighbors}</div><div class="l">邻域线索（范围外）</div></div>
    <div class="item"><div class="n">${c.ips}</div><div class="l">独立 IP</div></div>
    <div class="item"><div class="n">${c.requests}</div><div class="l">FOFA 请求（0 F 点）</div></div>
  </div>
  <p style="margin:10px 0 4px">流程（正常被动流程，与框架阶段一一对应）：</p>
  <ul>
    <li><b>Stage 3/4 被动子域收集</b>：FOFA domain 查询 + crt.sh 证书透明度 + RapidDNS 被动 DNS 聚合（对应 OneForAll 启用的被动模块同类源）→ ${c.subdomains} 个子域；</li>
    <li><b>Stage 5 DNS/CDN 观测</b>：${c.subdomains} 域名 × ${TKCN_RESOLVERS.length} 公共递归上游（${TKCN_RESOLVERS.join(" / ")}）A/CNAME 观测 → ${c.dnsResolved} 域名有解析、${c.cdnCname} 条 CDN CNAME 链、${c.inconsistent} 个多上游不一致（CDN/GEO 场景）；</li>
    <li><b>反馈查询</b>：已发现资产反哺——www 集群与 apex 的 IP 反查、整 C 段邻域扫描（共 ${c.neighbors} 条范围外线索：集团邻域根域/医院域、证书供应商、共租噪声、疑似仿冒均已分类隔离）、证书反查；ICP 主体反查受账户字段权限限制未成（详见表格台账）；</li>
    <li>结论：<b>值得进一步投入</b>——测试环境与 VPN 等难发现资产、供应链与集团邻域线索、疑似仿冒线索均已出现，且成本极低（${c.fpoints} F 点）。</li>
  </ul>
</div>

<div class="card">
  <h2>二、查询台账（FOFA 8 次搜索 + 3 次 info/my；间隔 ≥20s；当日熔断线 12）</h2>
  <table>
    <tr><th>tag</th><th>查询</th><th>轮次</th><th>总量</th><th>取回</th><th>置信度</th><th>F 点</th><th>状态</th></tr>
    ${queryRows(TKCN_QUERIES)}
  </table>
  <div class="cap">另：crt.sh / RapidDNS / 公共解析器 DNS 观测不属于 FOFA 配额；DNS 观测 37 域名 × 3 上游 × 2 类型 = 222 次公共解析器查询（不触目标）。</div>
</div>

<div class="card">
  <h2>三、候选资产（A 级查询 · host+port 去重 ${c.candidates} 条 · 全部 candidate_only）</h2>
  <img class="shot" src="data:image/png;base64,${TKCN_SHOT1}" alt="候选资产表">
  <div class="cap">▲ 截图 1/2：候选资产与 DNS/CDN 判读（与 report/tk.cn_delivery/evidence/ 原始 JSON 一一对应）。</div>
  <table>
    <tr><th>资产</th><th>IP</th><th>标题/产品</th><th>城市</th><th>DNS/CDN</th><th>发现要点</th></tr>
    ${candidateRows(TKCN_CANDIDATES)}
  </table>
</div>

<div class="card">
  <h2>四、反馈查询与邻域线索（范围外 · 不视为目标资产）</h2>
  <img class="shot" src="data:image/png;base64,${TKCN_SHOT2}" alt="邻域与反馈线索表">
  <div class="cap">▲ 截图 2/2：IP 反查 / C 段 / 证书反查命中的邻域、集团、供应商与疑似仿冒线索。</div>
  <table>
    <tr><th>资产</th><th>IP</th><th>类型</th><th>标题</th><th>判读</th></tr>
    ${neighborRows(TKCN_NEIGHBORS)}
  </table>
</div>

<div class="card">
  <h2>五、DNS 多上游观测（仅公共递归解析器；37 域名）</h2>
  <table>
    <tr><th>域名</th><th>判读</th><th>各上游观测</th></tr>
    ${dnsRows(TKCN_DNS)}
  </table>
  <div class="cap">多上游不一致 = CDN/GEO-DNS 场景（不同上游得到不同边缘地址），与框架「DNS 多上游观测」设计一致。</div>
</div>

<div class="card">
  <h2>六、重点发现与下一步（需授权后执行）</h2>
  <table>
    <tr><th style="width:240px">对象</th><th>发现</th><th style="width:250px">建议（授权后）</th></tr>
    ${highlights.map((h) => `<tr><td class="mono">${esc(h.host)}</td><td>${esc(h.note)}</td><td>纳入高价值清单，授权后核实</td></tr>`).join("")}
  </table>
  <div class="notice green" style="margin-top:12px"><b>配额与纪律</b>：本轮 FOFA 11 次请求 / 0 F 点 / 限速 20s；账户 VIP-2（剩余 F 点 58、免费额度 5000）。
  继续投入建议：翻页拉全 170/239/257 → 配置第二来源（Quake/Hunter/crt.sh）交叉佐证（C→A 需双来源）→ ICP 字段权限升级后做主体反查拉全集团根域。主动核实必须等书面授权。</div>
</div>

<div class="card">
  <h2>七、本轮不足（工具与方法）</h2>
  <ul>
    <li>单源单页：FOFA 仅第 1 页 20 条/查询（170/239/257 总量未拉全）；无第二来源交叉，全部停留候选态；</li>
    <li>字段受限：icp.name 在本账户不可用（820000，已探测确认）；last_updatetime 返回为空；证书 SAN 明细未取；</li>
    <li>被动源深度：crt.sh 对该域索引弱（仅 20 条、无子域 SAN）；OTX 免费接口限流未取得数据；</li>
    <li>框架缺口：前端此前无法消费真实证据（本轮已补被动试点视图与报告导出）；FOFA 适配器每次搜索附带 info/my（省配额优化待回流）；quota CLI 在输出目录不可写时崩溃；</li>
    <li>环境：受限 shell 不可写 data/docs/scripts/profiles（ACL）；Playwright/esbuild 需提权运行（环境边界）。</li>
  </ul>
</div>

<footer>暴露面收集框架 · tk.cn 被动试点轮 · 由前端工作台导出 · 内部资料，请勿外传 · 全部为第三方已索引数据的候选线索，未经目标侧确认</footer>
</div>
</body>
</html>`;
}

export function downloadPassivePilotReport(): string {
  const html = buildPassivePilotReportHtml();
  download("tk-cn-passive-report.html", "text/html", html);
  return html;
}

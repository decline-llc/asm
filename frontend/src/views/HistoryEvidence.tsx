import React, { useEffect, useMemo, useState } from "react";
import { TKCN_HAS_EVIDENCE, TKCN_META, TKCN_CANDIDATES, TKCN_DNS, TKCN_NEIGHBORS, TKCN_QUERIES, TKCN_SUBDOMAINS, TKCN_RESOLVERS } from "../data/tkcnEvidence";
import { downloadPassivePilotReport } from "../services/passiveReport";
import { downloadCsv, toCsv } from "../services/csv";
import { useFocusTrap } from "../components/useFocusTrap";
import "../history.css";

type Tab = "candidates" | "dns" | "neighbors" | "subdomains" | "ledger";
type Entry = { id: string; values: string[]; sources: string[]; raw: unknown };
type Section = { key: Tab; label: string; columns: string[]; entries: Entry[] };
const KINDS: Record<string, string> = { vendor: "供应商", anomaly: "疑似仿冒", group: "集团邻域", ip: "邻域 / IP", noise: "噪声" };
const PAGE_SIZE = 25;
const observedTime = (value: string) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "未记录";
const upstreams = (rows: { upstream: string; answers: string[]; cnameChain: string[]; status: string }[]) => rows.map(row => `${row.upstream} → ${[...row.answers, ...row.cnameChain].join("、") || row.status}`).join("\n");

function EvidenceDetail({ entry, section, onClose }: { entry: Entry; section: Section; onClose: () => void }) {
  const ref = useFocusTrap<HTMLDivElement>({ onClose });
  return <div className="history-modal-layer"><div className="history-backdrop" onClick={onClose} /><div className="history-detail" role="dialog" aria-modal="true" aria-labelledby="evidence-detail-title" tabIndex={-1} ref={ref}>
    <div className="history-detail-head"><div><small>{section.label} · 历史记录</small><h2 id="evidence-detail-title">{entry.values[0]}</h2></div><button className="btn" onClick={onClose} aria-label="关闭证据详情">关闭</button></div>
    <p className="history-context">{TKCN_META.org} · {TKCN_META.target} · {observedTime(TKCN_META.stamp)}（北京时间）</p>
    <dl className="history-fields">{section.columns.map((column, index) => <React.Fragment key={column}><dt>{column}</dt><dd>{entry.values[index] || "—"}</dd></React.Fragment>)}</dl>
    <p className="history-context">该条记录保留历史观测状态；候选资产与范围外线索按原始档案区分。</p>
    <details><summary>查看完整保存记录</summary><pre className="history-raw">{JSON.stringify(entry.raw, null, 2)}</pre></details>
  </div></div>;
}

export function HistoryEvidence() {
  const [tab, setTab] = useState<Tab>("candidates");
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [sort, setSort] = useState("original");
  const [view, setView] = useState<"table" | "list">(() => {
    try { return localStorage.getItem("asm-history:view") === "list" ? "list" : "table"; } catch { return "table"; }
  });
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [exportNotice, setExportNotice] = useState("");
  useEffect(() => {
    const previous = document.title;
    document.title = `${TKCN_META.org || "历史调查"} · 历史证据 | ASM`;
    return () => { document.title = previous; };
  }, []);
  useEffect(() => { try { localStorage.setItem("asm-history:view", view); } catch { /* Optional preference. */ } }, [view]);
  useEffect(() => { setPage(0); setSelected(null); }, [tab, query, source, sort]);
  const sections = useMemo<Section[]>(() => [
    { key: "candidates", label: "候选资产", columns: ["资产", "IP", "标题 / 产品", "发现来源", "DNS / CNAME", "发现要点"], entries: TKCN_CANDIDATES.map(row => ({ id: `${row.host}|${row.port}|${row.proto}|${row.ip}`, values: [`${row.host}:${row.port}`, row.ip, row.title || row.product, row.sources.join("、"), row.dns.cnameChain.join(" → ") || (row.dns.resolved ? row.dns.ips.join("、") : "无解析地址"), [...row.labels, ...(row.dns.inconsistent ? ["多上游不一致"] : [])].join("、")], sources: row.sources, raw: row })) },
    { key: "dns", label: "DNS 观测", columns: ["域名", "解析状态", "各上游保存观测"], entries: TKCN_DNS.map(row => ({ id: row.domain, values: [row.domain, row.upstreams.some(item => item.answers.length) ? "已有解析观测" : "未观测到地址记录", upstreams(row.upstreams)], sources: row.upstreams.map(item => item.upstream), raw: row })) },
    { key: "neighbors", label: "范围外线索", columns: ["线索资产", "IP", "类型", "标题 / 产品", "判读依据"], entries: TKCN_NEIGHBORS.map(row => ({ id: `${row.host}|${row.port}|${row.ip}|${row.kind}`, values: [`${row.host}:${row.port}`, row.ip, KINDS[row.kind] || row.kind, row.title || row.product, [row.note, ...row.why].filter(Boolean).join("\n")], sources: [], raw: row })) },
    { key: "subdomains", label: "子域", columns: ["子域", "发现来源"], entries: TKCN_SUBDOMAINS.map(row => ({ id: row.name, values: [row.name, row.sources.join("、")], sources: row.sources, raw: row })) },
    { key: "ledger", label: "采集台账", columns: ["查询标记", "查询条件", "轮次", "返回 / 总量", "查询精度", "F 点", "采集状态"], entries: TKCN_QUERIES.map(row => ({ id: row.tag, values: [row.tag, row.query, row.round, `${row.returned} / ${row.ok ? row.total : "未知"}`, row.confidence, String(row.fpoint), row.ok ? row.why || "成功" : row.error || "失败"], sources: ["FOFA"], raw: row })) },
  ], []);
  const section = sections.find(item => item.key === tab)!;
  const sources = [...new Set(section.entries.flatMap(item => item.sources))].sort();
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = section.entries.filter(item => (!source || item.sources.includes(source)) && (!needle || `${item.values.join(" ")} ${item.sources.join(" ")} ${JSON.stringify(item.raw)}`.toLowerCase().includes(needle)));
    return sort === "original" ? matches : [...matches].sort((a, b) => a.values[0].localeCompare(b.values[0], "zh-CN") * (sort === "desc" ? -1 : 1));
  }, [section, query, source, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const entries = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const exportCsv = () => {
    downloadCsv(`历史证据-${TKCN_META.target || "档案"}-${tab}.csv`, toCsv(section.columns, filtered.map(item => item.values)));
    setExportNotice(`已导出 ${section.label} 的 ${filtered.length} 条筛选结果。`);
  };
  return <div className="history-page">
    <header className="history-header"><a className="history-brand" href="/">ASM <span>调查档案</span></a><a className="btn" href="/">返回项目中心</a></header>
    <main className="history-main">
      <div className="history-title"><div><div className="history-eyebrow">历史证据 · {TKCN_HAS_EVIDENCE ? "已载入本地档案" : "等待载入"}</div><h1>{TKCN_HAS_EVIDENCE ? `${TKCN_META.org} · 互联网暴露面调查` : "历史调查证据"}</h1><p>{TKCN_META.target || "尚未载入调查对象"} · 证据整理于 {observedTime(TKCN_META.stamp)}（北京时间）</p></div><button className="btn primary" disabled={!TKCN_HAS_EVIDENCE} onClick={() => { downloadPassivePilotReport(); setExportNotice("已导出完整历史证据 HTML 报告。"); }}>导出完整 HTML 报告</button></div>
      <div className="history-summary"><div><strong>{TKCN_CANDIDATES.length}</strong><span>候选资产</span></div><div><strong>{TKCN_SUBDOMAINS.length}</strong><span>发现子域</span></div><div><strong>{TKCN_DNS.length}</strong><span>DNS 观测对象</span></div><div><strong>{TKCN_NEIGHBORS.length}</strong><span>范围外线索</span></div><div><strong>{TKCN_QUERIES.length}</strong><span>查询记录</span></div></div>
      <div className="history-archive-note"><span className="badge neutral">历史候选证据</span><span>资产保留待核实状态，范围外线索单独列出。</span><details><summary>档案口径与采集来源</summary><p>{TKCN_META.boundary || "尚无档案说明"}</p><p>DNS 观测上游：{TKCN_RESOLVERS.join("、") || "未记录"}。台账中的精度标注表示查询匹配精度。</p><p>原始证据保存在调查交付目录，完整 HTML 报告包含已有证据截图。</p></details></div>
      {!TKCN_HAS_EVIDENCE && <div className="history-empty"><h2>尚未载入历史证据</h2><p>完成本地交付证据的整理与导入后，可在此浏览调查对象、来源、原始观测和采集台账。</p></div>}
      {exportNotice && <p className="history-export-notice" role="status">{exportNotice}</p>}
      <section className="history-panel" aria-label="历史证据浏览">
        <div className="history-tabs" role="tablist" aria-label="证据分类">{sections.map(item => <button key={item.key} role="tab" aria-selected={tab === item.key} onClick={() => { setTab(item.key); setSource(""); }}>{item.label}<span>{item.entries.length}</span></button>)}</div>
        <div className="history-toolbar"><input aria-label="搜索历史证据" placeholder="搜索域名、IP、标题、来源或查询条件…" value={query} onChange={event => setQuery(event.target.value)} />{!!sources.length && <select aria-label="筛选证据来源" value={source} onChange={event => setSource(event.target.value)}><option value="">全部来源 / 上游</option>{sources.map(item => <option key={item}>{item}</option>)}</select>}<select aria-label="历史证据排序" value={sort} onChange={event => setSort(event.target.value)}><option value="original">保存顺序</option><option value="asc">名称升序</option><option value="desc">名称降序</option></select><div className="history-view-switch" role="group" aria-label="历史证据展示方式"><button aria-pressed={view === "table"} onClick={() => setView("table")}>表格</button><button aria-pressed={view === "list"} onClick={() => setView("list")}>列表</button></div><button className="btn" disabled={!filtered.length} onClick={exportCsv}>导出当前 CSV</button></div>
        <div className="history-result-bar"><span>{section.label} · 显示 {filtered.length} / {section.entries.length} 条</span>{(query || source) && <button className="btn ghost small" onClick={() => { setQuery(""); setSource(""); }}>清除筛选</button>}<small>点击记录名称查看证据详情</small></div>
        {view === "table" && <div className="history-table-wrap"><table><thead><tr>{section.columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{entries.map(entry => <tr key={entry.id}>{entry.values.map((value, index) => <td key={section.columns[index]}>{index === 0 ? <button className="history-record-link" onClick={() => setSelected(entry)}>{value}</button> : value || "—"}</td>)}</tr>)}</tbody></table></div>}
        {view === "list" && <div className="history-list">{entries.map(entry => <article key={entry.id}><button className="history-record-link" onClick={() => setSelected(entry)}>{entry.values[0]}</button><dl>{section.columns.slice(1).map((column, index) => <React.Fragment key={column}><dt>{column}</dt><dd>{entry.values[index + 1] || "—"}</dd></React.Fragment>)}</dl></article>)}</div>}
        {!entries.length && <div className="history-empty"><h3>{TKCN_HAS_EVIDENCE ? "没有匹配的历史记录" : "等待导入证据"}</h3><p>{TKCN_HAS_EVIDENCE ? "尝试调整搜索词或来源筛选。" : "载入本地调查档案后，此处将显示对应记录。"}</p></div>}
        <div className="history-pagination"><span>每页 {PAGE_SIZE} 条 · 第 {currentPage + 1} / {pageCount} 页</span><button className="btn small" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一页</button><button className="btn small" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>下一页</button></div>
      </section>
    </main>
    {selected && <EvidenceDetail entry={selected} section={section} onClose={() => setSelected(null)} />}
  </div>;
}

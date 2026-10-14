import React, { useEffect, useMemo, useState } from "react";
import type { ProjectRecord } from "../services/workbenchApi";
import { TKCN_HAS_EVIDENCE, TKCN_META } from "../data/tkcnEvidence";

type Purpose = "investigation" | "validation" | "demo";
type View = "cards" | "list" | "table";
const PURPOSES: [Purpose, string][] = [["investigation", "业务调查"], ["validation", "测试验收"], ["demo", "演示项目"]];
const STATES: Record<string, string> = { completed: "已完成", running: "执行中", paused: "已暂停", stopped: "已停止", interrupted: "已中断", partial: "部分完成", failed: "失败", pending: "等待" };
export const projectName = (item: ProjectRecord) => item.config?.name || item.config?.targets?.company || item.name || item.project_id;
const projectScope = (item: ProjectRecord) => [...(item.config?.targets?.roots || []), ...(item.config?.targets?.ip_cidrs || []), ...(item.config?.scope_sets?.investigation?.subjects || [])].join("、") || "尚未填写调查对象";
const formatTime = (value?: string) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "暂无记录";
const latest = (item: ProjectRecord) => item.runs?.[0];

export function ProjectCenter({ projects, loading, busy, canCreate, onOpen, onCreate, onRefresh, onHistory, onDemo }: {
  projects: ProjectRecord[]; loading: boolean; busy: boolean; canCreate: boolean;
  onOpen: (item: ProjectRecord) => void; onCreate: () => void; onRefresh: () => void;
  onHistory?: () => void; onDemo?: () => void;
}) {
  const [purpose, setPurpose] = useState<Purpose>("investigation");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("updated");
  const [view, setView] = useState<View>(() => {
    try { const saved = localStorage.getItem("asm-projects:view"); if (saved === "list" || saved === "table") return saved; } catch { /* Optional preference. */ }
    return "cards";
  });
  useEffect(() => { try { localStorage.setItem("asm-projects:view", view); } catch { /* Optional preference. */ } }, [view]);
  const category = projects.filter(item => (item.purpose || "investigation") === purpose);
  const visible = useMemo(() => category.filter(item => `${projectName(item)} ${projectScope(item)}`.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) => sort === "name" ? projectName(a).localeCompare(projectName(b), "zh-CN") : String(b.updated_at || "").localeCompare(String(a.updated_at || ""))), [projects, purpose, query, sort]);
  const status = (item: ProjectRecord) => item.status === "invalid_config" ? "配置需要修复" : STATES[latest(item)?.status] || latest(item)?.status || "尚未运行";
  const delivery = (item: ProjectRecord) => {
    const snapshot = latest(item)?.snapshot;
    if (!snapshot) return "尚无交付";
    try { const value = typeof snapshot === "string" ? JSON.parse(snapshot) : snapshot; return value.status === "complete" ? "交付完整" : "交付不完整"; }
    catch { return "交付状态待检查"; }
  };
  const openButton = (item: ProjectRecord) => <button className="wb-primary" disabled={item.status === "invalid_config"} onClick={() => onOpen(item)}>打开工作台</button>;
  return <section data-testid="project-center">
    <div className="wb-section-head"><div><h2>调查项目</h2><p className="wb-muted" style={{ margin: "5px 0 0" }}>围绕明确的企业、域名或目标组织调查；多次运行与报告保存在项目内。</p></div><div className="wb-actions"><button onClick={onRefresh} disabled={loading}>刷新</button><button className="wb-primary" disabled={!canCreate || busy} onClick={onCreate}>新建项目</button></div></div>
    <div className="wb-catalog-tabs" role="tablist" aria-label="项目用途">{PURPOSES.map(([key, label]) => <button key={key} role="tab" aria-selected={purpose === key} onClick={() => { setPurpose(key); setQuery(""); }}>{label}<span>{projects.filter(item => (item.purpose || "investigation") === key).length + (key === "demo" && onDemo ? 1 : 0)}</span></button>)}</div>
    <div className="wb-catalog-toolbar"><input aria-label="搜索调查项目" placeholder="搜索项目名称或调查对象…" value={query} onChange={event => setQuery(event.target.value)} /><select aria-label="项目排序" value={sort} onChange={event => setSort(event.target.value)}><option value="updated">最近更新优先</option><option value="name">按项目名称</option></select><div className="wb-view-switch" role="group" aria-label="项目展示方式">{([["cards", "卡片"], ["list", "列表"], ["table", "表格"]] as [View, string][]).map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => setView(key)}>{label}</button>)}</div></div>
    {purpose === "validation" && <p className="wb-muted">开发验收记录保留在此处。后续验收使用独立的测试数据目录。</p>}
    {purpose === "demo" && onDemo && <div className="wb-panel" style={{ marginBottom: 16 }}><h3>澄川科技集团 · 互联网暴露面调查</h3><p className="wb-muted">虚构演示项目，用于体验资产、证据和报告的组织方式。</p><button onClick={onDemo}>打开演示项目</button></div>}
    {loading && <p role="status">正在读取项目…</p>}
    {!loading && !visible.length && <div className="wb-empty"><h3>{query ? "没有匹配的项目" : purpose === "investigation" ? "开始一项明确目标的调查" : "此分类暂无项目"}</h3><p>{query ? "调整名称或调查对象的搜索条件。" : purpose === "investigation" ? "新建业务项目，填写调查对象与范围。已有历史证据也可从下方档案入口浏览。" : "该分类中的记录会显示在这里。"}</p></div>}
    {view === "table" && !!visible.length && <div className="wb-table-wrap wb-panel"><table><thead><tr><th>项目 / 调查对象</th><th>最近运行</th><th>更新时间</th><th>运行次数</th><th>交付</th><th>操作</th></tr></thead><tbody>{visible.map(item => <tr key={item.project_id}><td><strong>{projectName(item)}</strong><br /><small>{projectScope(item)}</small></td><td>{status(item)}<br /><small>{item.config?.execution?.source === "replay" ? "证据回放" : "实时采集"}</small></td><td>{formatTime(item.updated_at)}</td><td>{item.runs?.length || 0}</td><td>{delivery(item)}</td><td>{openButton(item)}</td></tr>)}</tbody></table></div>}
    {view !== "table" && <div className={view === "cards" ? "wb-projects" : "wb-project-list"}>{visible.map(item => <article className={`wb-project-card${view === "list" ? " wb-project-row" : ""}`} key={item.project_id}><div><h3>{projectName(item)}</h3><p className="wb-muted wb-project-scope">{projectScope(item)}</p><small>{formatTime(item.updated_at)} · 已留档运行 {item.runs?.length || 0} 次</small>{item.reason && <p>{item.reason}</p>}</div><div className="wb-project-state"><span className="wb-badge" data-state={latest(item)?.status}>{status(item)}</span><small>{delivery(item)}</small></div><div className="wb-actions">{openButton(item)}<details><summary>配置位置</summary><small className="wb-path">{item.path || "未保存"}</small></details></div></article>)}</div>}
    {purpose === "investigation" && onHistory && <article className="wb-panel wb-history-card"><div><span className="wb-badge">历史证据档案</span><h3>{TKCN_HAS_EVIDENCE ? `${TKCN_META.org} · ${TKCN_META.target} 暴露面调查` : "已有调查证据"}</h3><p className="wb-muted">{TKCN_HAS_EVIDENCE ? `${TKCN_META.counts.candidates} 条候选资产 · ${TKCN_META.counts.subdomains} 个子域 · 保存来源与采集台账` : "浏览本地留档的候选资产、DNS 观测与来源记录。"}</p></div><button onClick={onHistory}>浏览历史证据</button></article>}
  </section>;
}

import React, { useMemo, useState } from "react";
import { useStore } from "../services/store";
import { assetKey, diffNewAssetKeys } from "../data/dataset";
import { Badge, ConfBadge, LeadKindBadge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";

export function Overview() {
  const {
    companies, domains, assets, trusted, quarantine, leads, leadStatus,
    tasks, snapshots, project, navigate, openLead, openAsset, openDomain,
  } = useStore();

  // ---- 指标（统一数据集计算，写明统计口径） ----
  const pendingLeads = leads.filter((l) => leadStatus(l.id) === "pending");
  const domainCount = domains.length;
  // 与报告中心共用同一差分函数；快照只含可信主键，故差分即「新增可信资产」
  const changes = useMemo(() => diffNewAssetKeys(snapshots), [snapshots]);
  const newAssets = changes.added;
  // D+ 归属待核实线索数（仅提示，不计入可信新增）
  const pendingDPlus = leads.filter((l) => l.confidence === "D+" && leadStatus(l.id) === "pending").length;

  const stats = [
    {
      label: "可信资产",
      value: trusted.length,
      foot: "host+port+proto 去重；A/B 可信、C 需双来源佐证；D/D+ 不计入",
      icon: "check",
    },
    {
      label: "已收集域名",
      value: domainCount,
      foot: "含候选关系域名，去重后口径",
      icon: "globe",
    },
    {
      label: "待核对线索",
      value: pendingLeads.length,
      foot: `另有 ${quarantine.length} 条 D 级隔离候选`,
      icon: "evidence",
    },
    {
      label: "本轮新增可信资产",
      value: newAssets.length,
      foot: `${snapshots[0].runId} → ${snapshots[1].runId}${pendingDPlus ? `；另有 ${pendingDPlus} 条 D+ 待核实` : ""}`,
      icon: "plus",
    },
  ];

  // ---- 调查路径（公司 → 域名 → 服务） ----
  const [pathCid, setPathCid] = useState<string>("C001");
  const pathCompany = companies.find((c) => c.cid === pathCid)!;
  const pathDomains = domains.filter((d) => d.cid === pathCid);
  const [pathDomain, setPathDomain] = useState<string | null>(null);
  const pathAssets = pathDomain
    ? trusted.filter((a) => a.host === pathDomain)
    : [];

  // ---- 优先核对队列（写明原因） ----
  const priority = [...pendingLeads]
    .sort((a, b) => ({ high: 0, medium: 1, low: 2 }[a.severity] as number) - ({ high: 0, medium: 1, low: 2 }[b.severity] as number))
    .slice(0, 5);

  const stageStatus = (i: number): "done" | "warn" | "pending" => {
    const run = tasks.find((t) => t.id === project.currentRun);
    const st = run?.stages[i];
    if (!st) return "pending";
    if (st.status === "done") return "done";
    if (st.status === "failed") return "warn";
    return "pending";
  };

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>项目概览</h2>
        <span className="desc">
          {project.name} · 范围 {project.seeds.rootDomains.join("、")} ·{" "}
          {project.mode === "passive" ? "被动采集" : "主动"} · 运行{" "}
          <span className="mono">{project.currentRun}</span>
        </span>
      </div>

      {/* 主指标 */}
      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        {stats.map((s) => (
          <div className="panel stat-card" key={s.label}>
            <div className="label">
              <Icon name={s.icon} size={14} />
              {s.label}
            </div>
            <div className="value">{s.value}</div>
            <div className="foot">{s.foot}</div>
          </div>
        ))}
      </div>

      <div className="grid cols-2" style={{ marginBottom: 14 }}>
        {/* 调查路径 */}
        <section className="panel">
          <div className="panel-head">
            <Icon name="graph" size={15} />
            <h3>调查路径</h3>
            <span className="hint">公司 → 域名 → 服务，逐层探索</span>
          </div>
          <div className="panel-body trail-path">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              {companies.map((c) => (
                <button
                  key={c.cid}
                  className={`btn small ${pathCid === c.cid ? "primary" : ""}`}
                  onClick={() => {
                    setPathCid(c.cid);
                    setPathDomain(null);
                  }}
                >
                  {c.brand}
                  {c.sharePct != null && ` ${c.sharePct}%`}
                </button>
              ))}
            </div>
            <button
              className="trail-node"
              onClick={() => navigate("graph")}
              title="在关系图谱中查看股权结构"
            >
              <span className="depth" style={{ background: "var(--accent)" }} />
              <span className="k">公司</span>
              <span className="v">{pathCompany.name}</span>
              {pathCompany.sharePct != null && (
                <Badge tone={pathCompany.sharePct >= 50 ? "ok" : "warn"}>
                  持股 {pathCompany.sharePct}%
                </Badge>
              )}
              <span className="go">图谱 →</span>
            </button>
            <div className="trail-children">
              {pathDomains.map((d) => (
                <React.Fragment key={d.domain}>
                  <button
                    className="trail-node"
                    onClick={() => setPathDomain(pathDomain === d.domain ? null : d.domain)}
                    aria-expanded={pathDomain === d.domain}
                  >
                    <span className="depth" style={{ background: "#4a90b8" }} />
                    <span className="k">域名</span>
                    <span className="v">{d.domain}</span>
                    <ConfBadge c={d.confidence} />
                    <span className="go">{pathDomain === d.domain ? "收起" : "展开"}</span>
                  </button>
                  {pathDomain === d.domain && (
                    <div className="trail-children">
                      {pathAssets.length === 0 && (
                        <div style={{ padding: "6px 12px", color: "var(--ink-3)", fontSize: 12 }}>
                          该域名下暂无可信服务（可能存在候选或异常观测）
                        </div>
                      )}
                      {pathAssets.map((a) => (
                        <button
                          key={assetKey(a)}
                          className="trail-node"
                          onClick={() => openAsset(assetKey(a))}
                        >
                          <span className="depth" style={{ background: "#7d5fd3" }} />
                          <span className="k">服务</span>
                          <span className="v">
                            :{a.port}/{a.proto} · {a.title || a.service}
                          </span>
                          <span className="go">详情 →</span>
                        </button>
                      ))}
                      <button className="trail-node" onClick={() => openDomain(d.domain)}>
                        <span className="depth" style={{ background: "var(--amber)" }} />
                        <span className="k">证据</span>
                        <span className="v">DNS 观测 / 来源 / 复核线索</span>
                        <span className="go">打开 →</span>
                      </button>
                    </div>
                  )}
                </React.Fragment>
              ))}
              {pathDomains.length === 0 && (
                <div style={{ padding: "6px 12px", color: "var(--ink-3)", fontSize: 12 }}>
                  暂无归属该企业的域名记录
                </div>
              )}
            </div>
          </div>
        </section>

        {/* 优先核对队列 */}
        <section className="panel">
          <div className="panel-head">
            <Icon name="warn" size={15} />
            <h3>建议优先核对</h3>
            <span className="hint">{pendingLeads.length} 条待核对</span>
            <button className="btn ghost small" style={{ marginLeft: "auto" }} onClick={() => navigate("review")}>
              全部 →
            </button>
          </div>
          <div className="panel-body" style={{ padding: "10px 12px" }}>
            {priority.map((l) => (
              <button className="lead-item" key={l.id} onClick={() => openLead(l.id)}>
                <div className="row1">
                  <LeadKindBadge kind={l.kind} />
                  <b style={{ fontSize: 12 }}>{l.id}</b>
                </div>
                <div className="target">{l.target}</div>
                <div className="reason">{l.reason}</div>
              </button>
            ))}
            {priority.length === 0 && (
              <div className="empty">
                <div className="ico">✓</div>
                所有线索均已处理
              </div>
            )}
          </div>
        </section>
      </div>

      {/* 采集流程 */}
      <section className="panel" style={{ marginBottom: 14 }}>
        <div className="panel-head">
          <Icon name="refresh" size={15} />
          <h3>采集流程</h3>
          <span className="hint">顺序执行；P1/P2 为独立线索轨道（同样顺序执行，非并发调度）</span>
        </div>
        <div className="panel-body">
          <div className="pipeline">
            {project.stages.map((s, i) => (
              <div className="step" key={s}>
                {i > 0 && <span className="arrow" />}
                <span className={`node ${stageStatus(i)}`}>
                  {stageStatus(i) === "done" && "✓ "}
                  {stageStatus(i) === "warn" && "⚠ "}
                  {s}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid cols-2">
        {/* 近期资产变化（快照对照入口） */}
        <section className="panel">
          <div className="panel-head">
            <Icon name="clock" size={15} />
            <h3>近期资产变化</h3>
            <span className="hint">两次运行快照对照（演示扩展字段）</span>
          </div>
          <div className="panel-body">
            <div className="report-table-note">
              对照：<span className="mono">{snapshots[0].runId}</span> →{" "}
              <span className="mono">{snapshots[1].runId}</span>
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.8 }}>
              <li>
                新增可信资产 <b>{newAssets.length}</b> 个（
                {newAssets.map((k) => k.split("|").slice(0, 2).join(":")).join("、") || "无"}
                ）
                {pendingDPlus > 0 && <>；另有 <b>{pendingDPlus}</b> 条 D+ 归属待核实（不计入可信）</>}
              </li>
              <li>
                离开可信集 <b>{changes.removed.length}</b> 项（
                {changes.removed.map((k) => k.split("|").slice(0, 2).join(":")).join("、") || "无"}
                ）；可能为归属或置信度变化，需要复核。
              </li>
              {snapshots[1].changedFields.map((c, i) => (
                <li key={i}>
                  字段变化 <span className="mono">{c.key}</span> 的 <b>{c.field}</b>：
                  <span style={{ color: "var(--ink-3)" }}>{c.from}</span> → {c.to}
                </li>
              ))}
              <li>新待核对项 <b>{snapshots[1].newLeads}</b> 条</li>
            </ul>
            <button className="btn small" style={{ marginTop: 10 }} onClick={() => navigate("assets")}>
              进入资产探索
            </button>
          </div>
        </section>

        {/* 最近任务 */}
        <section className="panel">
          <div className="panel-head">
            <Icon name="task" size={15} />
            <h3>最近任务</h3>
          </div>
          <div className="panel-body" style={{ padding: "8px 12px" }}>
            {tasks.slice(0, 3).map((t) => (
              <button
                key={t.id}
                className="lead-item"
                onClick={() => navigate("tasks", { taskId: t.id })}
              >
                <div className="row1">
                  <Badge
                    tone={
                      t.status === "done" ? "ok" : t.status === "partial-failed" ? "warn" : t.status === "failed" ? "danger" : "info"
                    }
                  >
                    {{ done: "已完成", "partial-failed": "部分失败", failed: "失败", running: "进行中", pending: "排队中" }[t.status]}
                  </Badge>
                  <b className="mono" style={{ fontSize: 12 }}>{t.id}</b>
                </div>
                <div className="target" style={{ fontFamily: "var(--sans)" }}>{t.name}</div>
                <div className="reason">
                  {t.mode === "passive" ? "被动模式" : "主动模式"} ·{" "}
                  {t.stages.filter((s) => s.status === "done").length}/{t.stages.length} 阶段完成
                </div>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

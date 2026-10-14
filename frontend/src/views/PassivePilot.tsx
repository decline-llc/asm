// ============================================================
// 被动试点视图：tk.cn 纯被动信息收集的真实证据展示。
// 数据由 report/tk.cn_delivery/tools/tkcn_build_dataset.py 生成（data/tkcnEvidence.local.ts，不入库）。
// 口径：全部候选（candidate_only），绝不计入可信资产；
// 本视图自包含，不读写演示数据集的 store 数据。
// ============================================================
import React, { useMemo, useState } from "react";
import {
  TKCN_META,
  TKCN_HAS_EVIDENCE,
  TKCN_QUERIES,
  TKCN_CANDIDATES,
  TKCN_NEIGHBORS,
  TKCN_DNS,
  TKCN_SUBDOMAINS,
  TKCN_RESOLVERS,
  type PilotNeighbor,
} from "../data/tkcnEvidence";
import { downloadPassivePilotReport } from "../services/passiveReport";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";

const NEIGHBOR_KIND: Record<PilotNeighbor["kind"], string> = {
  vendor: "供应商",
  anomaly: "疑似仿冒",
  group: "集团邻域",
  ip: "邻域/IP",
  noise: "噪声",
};

type Tab = "candidates" | "dns" | "neighbors" | "subdomains" | "ledger";

export function PassivePilot() {
  const c = TKCN_META.counts;
  const [tab, setTab] = useState<Tab>("candidates");
  const [q, setQ] = useState("");
  const [exported, setExported] = useState(false);

  const needle = q.trim().toLowerCase();
  const filter = <T extends { host?: string; domain?: string; name?: string; title?: string }>(rows: T[]): T[] =>
    !needle
      ? rows
      : rows.filter((r) =>
          [r.host, r.domain, r.name, r.title].filter(Boolean).join(" ").toLowerCase().includes(needle),
        );

  const candidates = useMemo(() => filter(TKCN_CANDIDATES), [needle]);
  const neighbors = useMemo(() => filter(TKCN_NEIGHBORS), [needle]);
  const dns = useMemo(() => filter(TKCN_DNS), [needle]);
  const subdomains = useMemo(() => filter(TKCN_SUBDOMAINS), [needle]);

  const onExport = () => {
    downloadPassivePilotReport();
    setExported(true);
  };

  const stats = [
    { label: "发现子域", value: c.subdomains, foot: "FOFA + crt.sh + RapidDNS + DNS 观测并集", icon: "globe" },
    { label: "候选资产", value: c.candidates, foot: "host+port 去重；全部 candidate_only", icon: "assets" },
    { label: "DNS 解析", value: c.dnsResolved, foot: `仅公共解析器（${TKCN_RESOLVERS.join("/")}）`, icon: "link" },
    { label: "CDN / CNAME", value: c.cdnCname, foot: `多上游不一致 ${c.inconsistent} 个（CDN/GEO 场景）`, icon: "graph" },
    { label: "邻域线索", value: c.neighbors, foot: `供应商 ${c.vendors} · 疑似仿冒 ${c.anomalies}（范围外）`, icon: "evidence" },
    { label: "独立 IP", value: c.ips, foot: `城市 ${c.cities} 处`, icon: "dashboard" },
  ];

  const tabs: [Tab, string][] = [
    ["candidates", `候选资产 ${c.candidates}`],
    ["dns", `DNS 观测 ${TKCN_DNS.length}`],
    ["neighbors", `邻域与反馈 ${c.neighbors}`],
    ["subdomains", `子域 ${c.subdomains}`],
    ["ledger", "查询台账"],
  ];

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>被动试点 · {TKCN_META.target || "（未载入证据）"}</h2>
        <span className="desc">
          {TKCN_META.org} · 真实被动证据 · 全部候选 · 未授权阶段
          {TKCN_META.stamp ? (
            <>
              {" "}· 生成（UTC）<span className="mono">{TKCN_META.stamp}</span>
            </>
          ) : null}
        </span>
        <div className="page-actions" style={{ marginLeft: "auto" }}>
          <button className="btn primary" onClick={onExport} disabled={!TKCN_HAS_EVIDENCE}>
            <Icon name="download" size={15} /> 导出 HTML 报告（含 2 张截图）
          </button>
        </div>
      </div>

      {!TKCN_HAS_EVIDENCE && (
        <div className="notice warn" style={{ marginBottom: 14 }}>
          <b>未载入真实证据。</b>真实证据含目标数据，不入 git——请先运行
          <code>python report/tk.cn_delivery/tools/tkcn_package_delivery.py</code>（生成交付目录）与
          <code>python report/tk.cn_delivery/tools/tkcn_build_dataset.py</code>（聚合生成
          <code>frontend/src/data/tkcnEvidence.local.ts</code>，已在 .gitignore 排除），再重新构建。
        </div>
      )}

      <div className="notice danger" style={{ marginBottom: 14 }}>
        <b>边界声明：</b>零发包——全程未向 {TKCN_META.target || "目标"} 及其任何子域 / 权威 NS / 解析 IP 发送任何数据包。DNS 仅查询公共递归解析器（
        {TKCN_RESOLVERS.join(" / ")}）；搜索引擎仅 fofa.info API（限速 ≥20s，当日 {c.requests} 次请求 /{" "}
        {c.fpoints} F 点，熔断线 12 次/日）。全部条目均为候选线索，<b>不构成核实资产、不计入可信统计</b>
        ；正式核实需书面授权。
        {exported && (
          <div style={{ marginTop: 6 }}>
            <span className="badge ok">已导出</span> 单文件 HTML 报告（含两张本地渲染证据表格截图，离线可开）。
          </div>
        )}
      </div>

      <div className="grid cols-3" style={{ gridTemplateColumns: "repeat(6, 1fr)", marginBottom: 14 }}>
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

      <div className="panel" style={{ padding: "12px 14px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {tabs.map(([key, label]) => (
            <button
              key={key}
              className={`pilot-chip ${tab === key ? "active" : ""}`}
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
          <input
            className="pilot-search"
            style={{ marginLeft: "auto" }}
            placeholder="过滤 host / 标题…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="过滤被动试点数据"
          />
        </div>
      </div>

      <div className="panel" style={{ marginTop: 12, padding: 0 }}>
        {tab === "candidates" && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>资产 host:port</th>
                  <th>IP</th>
                  <th>标题 / 产品</th>
                  <th>城市</th>
                  <th>DNS / CDN 判读</th>
                  <th>发现要点</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((a) => (
                  <tr key={`${a.host}:${a.port}`}>
                    <td className="mono">
                      {a.host}:{a.port}
                    </td>
                    <td className="mono">{a.ip}</td>
                    <td>{a.title || a.product || "—"}</td>
                    <td>{a.city || "—"}</td>
                    <td style={{ fontSize: 11.5 }}>
                      {a.dns.cnameChain.length
                        ? `CDN：${a.dns.cnameChain.join(" → ")}`
                        : a.dns.resolved
                          ? `解析 ${a.dns.ips.length} 个 IP`
                          : "无 A 记录"}
                      {a.dns.inconsistent && "（多上游不一致）"}
                    </td>
                    <td>
                      {a.labels.length > 0 ? (
                        a.labels.map((l) => (
                          <span key={l} className="badge neutral" style={{ marginRight: 4 }}>
                            {l}
                          </span>
                        ))
                      ) : (
                        <span style={{ color: "var(--ink-3)" }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {candidates.length === 0 && (
                  <tr>
                    <td colSpan={6} className="empty" style={{ padding: 24, textAlign: "center" }}>
                      没有匹配的候选资产
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {tab === "dns" && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>域名</th>
                  <th>判读</th>
                  <th>各上游观测</th>
                </tr>
              </thead>
              <tbody>
                {dns.map((d) => {
                  const resolved = d.upstreams.some((u) => u.answers.length > 0);
                  const inconsistent =
                    new Set(
                      d.upstreams.filter((u) => u.answers.length).map((u) => u.answers.slice().sort().join(",")),
                    ).size > 1;
                  return (
                    <tr key={d.domain}>
                      <td className="mono">{d.domain}</td>
                      <td>
                        {resolved ? (d.upstreams.some((u) => u.cnameChain.length) ? "CDN / CNAME" : "直连解析") : "无 A 记录"}
                        {inconsistent && (
                          <span className="badge warn" style={{ marginLeft: 6 }}>
                            多上游不一致
                          </span>
                        )}
                      </td>
                      <td style={{ fontSize: 11.5, fontFamily: "var(--mono)" }}>
                        {d.upstreams.map((u) => (
                          <div key={u.upstream}>
                            {u.upstream} →{" "}
                            {u.answers.length
                              ? u.answers.join(", ")
                              : u.cnameChain.length
                                ? u.cnameChain.join(" → ")
                                : u.status}
                          </div>
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {tab === "neighbors" && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>资产 host:port</th>
                  <th>IP</th>
                  <th>类型</th>
                  <th>标题</th>
                  <th>判读（范围外 · 不视为目标资产）</th>
                </tr>
              </thead>
              <tbody>
                {neighbors.map((n) => (
                  <tr key={`${n.host}:${n.port}`}>
                    <td className="mono">
                      {n.host}:{n.port}
                    </td>
                    <td className="mono">{n.ip}</td>
                    <td>
                      <span
                        className={`badge ${n.kind === "anomaly" ? "danger" : n.kind === "vendor" ? "info" : n.kind === "group" ? "demo" : "neutral"}`}
                      >
                        {NEIGHBOR_KIND[n.kind]}
                      </span>
                    </td>
                    <td>{n.title || "—"}</td>
                    <td style={{ fontSize: 11.5 }}>{n.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "subdomains" && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>子域</th>
                  <th>发现来源</th>
                </tr>
              </thead>
              <tbody>
                {subdomains.map((s) => (
                  <tr key={s.name}>
                    <td className="mono">{s.name}</td>
                    <td>
                      {s.sources.map((src) => (
                        <span key={src} className="badge neutral" style={{ marginRight: 4 }}>
                          {src}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "ledger" && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>tag</th>
                  <th>查询</th>
                  <th>轮次</th>
                  <th>总量</th>
                  <th>取回</th>
                  <th>置信度</th>
                  <th>F 点</th>
                  <th>状态 / 说明</th>
                </tr>
              </thead>
              <tbody>
                {TKCN_QUERIES.map((query) => (
                  <tr key={query.tag}>
                    <td className="mono">{query.tag}</td>
                    <td className="mono" style={{ fontSize: 11.5 }}>
                      {query.query}
                    </td>
                    <td>{query.round}</td>
                    <td className="num">{query.ok ? query.total : "—"}</td>
                    <td className="num">{query.returned}</td>
                    <td>{query.confidence}</td>
                    <td className="num">{query.fpoint}</td>
                    <td style={{ fontSize: 11.5 }}>
                      {query.ok ? (
                        query.why || "成功"
                      ) : (
                        <span className="badge danger">{query.error}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 10 }}>
        口径说明：候选资产来自 FOFA domain 查询（A 级查询精度），但按人工调用约定（docs/reference/api.md
        §3）保持 candidate_only，不进入可信统计；范围外命中（邻域/集团/供应商/疑似仿冒）单列，绝不混入候选。
        证据原始文件：report/tk.cn_delivery/evidence/（FOFA 原始 JSON + 候选 JSONL + DNS 观测 + 被动子域源）；
        工具调用痕迹：report/tk.cn_delivery/logs/tool-calls.jsonl。
      </p>
    </div>
  );
}

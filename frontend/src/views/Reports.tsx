import React, { useMemo, useState } from "react";
import { useStore } from "../services/store";
import { trustedAssets, assetKey, diffNewAssetKeys } from "../data/dataset";
import type { ReportTableKey } from "../types";
import { Badge, ConfBadge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";
import { downloadCsv, toCsv } from "../services/csv";

const TABLE_META: { key: ReportTableKey; label: string; map: string }[] = [
  { key: "master", label: "总表", map: "master（隔离候选不进入）" },
  { key: "equity", label: "股权结构", map: "equity" },
  { key: "domains", label: "域名明细", map: "domains" },
  { key: "ips", label: "IP 明细", map: "ips" },
  { key: "urls", label: "URL 明细", map: "urls" },
  { key: "systems", label: "系统指纹", map: "systems" },
  { key: "social", label: "社交/人员（脱敏）", map: "social" },
  { key: "todos", label: "待办线索", map: "todos" },
];

export function Reports() {
  const { assets, domains, companies, leads, quarantine, snapshots, project } =
    useStore();
  const [view, setView] = useState<"summary" | "detail">("summary");
  const [table, setTable] = useState<ReportTableKey>("master");

  const trusted = useMemo(() => trustedAssets(assets), [assets]);

  const tableData = useMemo((): { headers: string[]; rows: unknown[][] } => {
    const cname = (cid: string | null) => companies.find((c) => c.cid === cid)?.brand ?? "未确认";
    switch (table) {
      case "master":
        return {
          headers: ["序号", "资产", "端口", "标题", "技术栈", "等级标注", "来源", "置信度", "截图链接"],
          rows: trusted.map((a, i) => [
            i + 1, a.host, a.port, a.title, a.tech.join("; "),
            a.labels.join("; ") || "—", a.sources.join("; "), a.confidence,
            a.screenshot.status === "captured" ? a.screenshot.file : `（${a.screenshot.status}）`,
          ]),
        };
      case "equity":
        return {
          headers: ["公司", "品牌", "母公司", "持股比例%", "层级", "来源", "备注"],
          rows: companies.map((c) => [
            c.name, c.brand, companies.find((p) => p.cid === c.parentCid)?.brand ?? "—",
            c.sharePct ?? "—", c.level, c.source, c.note,
          ]),
        };
      case "domains":
        return {
          headers: ["域名", "根域", "五类标注", "置信度", "选用地址", "来源", "最近观测"],
          rows: domains.map((d) => [
            d.domain, d.registrable, d.tag5, d.confidence,
            d.selectedIps.join("; ") || "未选用", d.sources.join("; "), d.lastSeen,
          ]),
        };
      case "ips": {
        const m = new Map<string, string[]>();
        trusted.forEach((a) => {
          m.set(a.ip, [...(m.get(a.ip) ?? []), `${a.host}:${a.port}`]);
        });
        return {
          headers: ["IP", "类型", "服务数", "资产"],
          rows: [...m.entries()].map(([ip, list]) => [
            ip, ip.includes(":") ? "IPv6" : "IPv4", list.length, list.join("; "),
          ]),
        };
      }
      case "urls":
        return {
          headers: ["URL", "标题", "技术栈", "截图状态", "最近观测"],
          rows: trusted.filter((a) => a.url).map((a) => [
            a.url, a.title, a.tech.join("; "), a.screenshot.status, a.lastSeen,
          ]),
        };
      case "systems":
        return {
          headers: ["资产", "服务", "产品", "版本", "指纹摘要"],
          rows: trusted.map((a) => [
            `${a.host}:${a.port}`, a.service, a.product || "—", a.version || "—", a.fingerprint ?? "—",
          ]),
        };
      case "social":
        return {
          headers: ["姓名", "角色", "联系方式", "来源"],
          rows: [
            ["张**（脱敏）", "技术负责人（演示）", "z***@example.com", "OSINT 演示"],
            ["李**（脱敏）", "域名管理员（演示）", "l***@example.com", "ICP 备案演示"],
          ],
        };
      case "todos":
        return {
          headers: ["编号", "类型", "对象", "异常原因", "建议下一步", "观测时间"],
          rows: leads.map((l) => [l.id, l.kind, l.target, l.reason, l.suggestion, l.ts]),
        };
    }
  }, [table, trusted, domains, companies, leads]);

  const exportCsv = () => {
    downloadCsv(
      `asm-${TABLE_META.find((t) => t.key === table)!.map.split("（")[0]}-${project.currentRun}-演示数据导出.csv`,
      toCsv(tableData.headers, tableData.rows)
    );
  };

  // 与概览共用同一差分函数；快照只含可信主键，差分即「新增可信资产」
  const changes = useMemo(() => diffNewAssetKeys(snapshots), [snapshots]);
  const newKeys = changes.added;
  const newCount = newKeys.length;
  const pendingDPlus = leads.filter((l) => l.confidence === "D+").length;

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>报告中心</h2>
        <span className="desc">八张表预览与筛选后 CSV 下载；XLSX / 内嵌 PNG 的独立 HTML 由后端生成，待接入</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn small" onClick={() => window.print()}>
            <Icon name="report" size={13} /> 打印布局
          </button>
          <button className="btn small" disabled title="后端生成 XLSX，前端待接入，不空点成功">
            XLSX 下载（待接入）
          </button>
          <button className="btn small" disabled title="后端生成内嵌 PNG 的独立 HTML，前端待接入，不空点成功">
            HTML 报告（待接入）
          </button>
        </div>
      </div>

      <div className="tabs panel" style={{ borderRadius: "10px 10px 0 0" }}>
        <button className={view === "summary" ? "active" : ""} onClick={() => setView("summary")}>汇报视图</button>
        <button className={view === "detail" ? "active" : ""} onClick={() => setView("detail")}>工程明细</button>
      </div>

      {view === "summary" && (
        <div className="panel" style={{ borderTop: 0, borderRadius: "0 0 10px 10px" }}>
          <div className="panel-body">
            <h3 style={{ margin: "0 0 10px", fontSize: 15 }}>{project.name} · 互联网暴露面调查汇报</h3>
            <dl className="fields" style={{ maxWidth: 640 }}>
              <dt>运行批次</dt><dd className="mono">{project.currentRun}</dd>
              <dt>采集模式</dt><dd>被动采集（演示数据）</dd>
              <dt>可信资产</dt><dd><b>{trusted.length}</b> 个（host+port+proto 去重，D/D+ 隔离候选不计入）</dd>
              <dt>已收集域名</dt><dd><b>{domains.length}</b> 个</dd>
              <dt>较上轮变化</dt><dd>新增可信资产 <b>{newCount}</b> 个（{newKeys.map((k) => k.split("|").slice(0, 2).join(":")).join("、") || "无"}）；新待核对项 <b>{snapshots[1].newLeads}</b> 条</dd>
              <dt>离开可信集</dt><dd><b>{changes.removed.length}</b> 项（{changes.removed.map((k) => k.split("|").slice(0, 2).join(":")).join("、") || "无"}）；归属或置信度变化需复核。</dd>
              <dt>待核对</dt><dd><b>{leads.length}</b> 条线索（DNS 冲突、假地址、归属待核实、采集失败等），其中 D+ 归属待核实 <b>{pendingDPlus}</b> 条不计入可信</dd>
              <dt>隔离区</dt><dd><b>{quarantine.length}</b> 条 D 级候选（永不进入可信统计）</dd>
            </dl>
            <div className="notice warn" style={{ marginTop: 14, maxWidth: 720 }}>
              <Icon name="warn" size={14} />
              重点关注：lab.example.com 上游 DNS 冲突（198.18.0.0/15 假地址观测）；
              C004 参股公司授权范围待确认；legacy.example.com 悬空 CNAME 候选待核对。
            </div>
          </div>
        </div>
      )}

      {view === "detail" && (
        <div className="panel" style={{ borderTop: 0, borderRadius: "0 0 10px 10px" }}>
          <div className="filter-bar">
            {TABLE_META.map((t) => (
              <button
                key={t.key}
                className={`btn small ${table === t.key ? "primary" : ""}`}
                onClick={() => setTable(t.key)}
                title={`映射：${t.map}`}
              >
                {t.label}
              </button>
            ))}
            <button className="btn small" style={{ marginLeft: "auto" }} onClick={exportCsv}>
              <Icon name="download" size={13} /> 下载本表 CSV（演示数据导出）
            </button>
          </div>
          <div style={{ padding: "8px 16px 0" }}>
            <div className="report-table-note">
              映射：{TABLE_META.find((t) => t.key === table)!.map} · 共 {tableData.rows.length} 行 ·
              CSV 已处理引号、换行、中文与公式前缀转义
            </div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 480, overflowY: "auto" }}>
            <table className="data">
              <thead>
                <tr>{tableData.headers.map((h) => <th key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {tableData.rows.map((r, i) => (
                  <tr key={i} style={{ cursor: "default" }}>
                    {r.map((c, j) => {
                      const s = String(c ?? "");
                      const isConf = tableData.headers[j] === "置信度" && /^[A-F]\+?$/.test(s);
                      return (
                        <td key={j} className={j === 0 || /^[\d.:/|a-z-]+$/i.test(s) ? "mono" : ""} style={{ fontSize: 12 }}>
                          {isConf ? <ConfBadge c={s as never} /> : s || "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

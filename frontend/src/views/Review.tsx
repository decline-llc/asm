import React, { useMemo, useState } from "react";
import { useStore } from "../services/store";
import { Badge, ConfBadge, LeadKindBadge, SeverityBadge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";
import { AssetDrawer } from "../components/AssetDrawer";
import type { LeadStatus } from "../types";

const STATUS_LABEL: Record<LeadStatus, string> = {
  pending: "待复核",
  reviewed: "已复核",
  excluded: "已排除",
};

export function Review() {
  const {
    leads, selection, openLead, leadStatus, leadNotes, leadHistory,
    setLeadStatus, addLeadNote, assets, openAsset, clearSelection, resetDemo,
  } = useStore();

  const [fStatus, setFStatus] = useState<"" | LeadStatus>("");
  const [noteDraft, setNoteDraft] = useState("");

  const filtered = useMemo(
    () => leads.filter((l) => !fStatus || leadStatus(l.id) === fStatus),
    [leads, fStatus, leadStatus]
  );

  const current = selection.leadId
    ? leads.find((l) => l.id === selection.leadId)
    : filtered[0];

  const selectedAsset = selection.assetKey
    ? assets.find((a) => `${a.host}|${a.port}|${a.proto}` === selection.assetKey)
    : undefined;

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>证据复核</h2>
        <span className="desc">
          状态与备注仅持久化在本地演示数据（localStorage）· 置信度与严重程度分开展示
        </span>
        <button className="btn small ghost" style={{ marginLeft: "auto" }} onClick={() => {
          if (window.confirm("重置演示数据：清除本地备注、状态与演示任务？")) resetDemo();
        }}>
          <Icon name="refresh" size={13} /> 重置演示
        </button>
      </div>

      <div className="review-layout">
        {/* 左侧线索队列 */}
        <div>
          <div className="filter-bar panel" style={{ borderRadius: 10, marginBottom: 10 }}>
            <select value={fStatus} onChange={(e) => setFStatus(e.target.value as "" | LeadStatus)} aria-label="按状态筛选">
              <option value="">状态：全部（{leads.length}）</option>
              <option value="pending">待复核（{leads.filter((l) => leadStatus(l.id) === "pending").length}）</option>
              <option value="reviewed">已复核（{leads.filter((l) => leadStatus(l.id) === "reviewed").length}）</option>
              <option value="excluded">已排除（{leads.filter((l) => leadStatus(l.id) === "excluded").length}）</option>
            </select>
            <span className="count-note">{filtered.length} 条</span>
          </div>
          <div role="list" aria-label="线索队列">
            {filtered.map((l) => {
              const st = leadStatus(l.id);
              return (
                <button
                  key={l.id}
                  role="listitem"
                  className={`lead-item ${current?.id === l.id ? "active" : ""}`}
                  onClick={() => openLead(l.id)}
                >
                  <div className="row1">
                    <LeadKindBadge kind={l.kind} />
                    <SeverityBadge s={l.severity} />
                    <span style={{ marginLeft: "auto" }}>
                      <Badge tone={st === "pending" ? "warn" : st === "reviewed" ? "ok" : "neutral"}>
                        {STATUS_LABEL[st]}
                      </Badge>
                    </span>
                  </div>
                  <div className="target">{l.target}</div>
                  <div className="reason">{l.reason}</div>
                </button>
              );
            })}
            {filtered.length === 0 && (
              <div className="empty panel">
                <div className="ico">∅</div>
                当前筛选下没有线索
              </div>
            )}
          </div>
        </div>

        {/* 右侧证据工作台 */}
        {current && (
          <div className="panel">
            <div className="panel-head">
              <LeadKindBadge kind={current.kind} />
              <h3 className="mono" style={{ wordBreak: "break-all" }}>{current.target}</h3>
              <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                {(["pending", "reviewed", "excluded"] as LeadStatus[]).map((s) => (
                  <button
                    key={s}
                    className={`btn small ${leadStatus(current.id) === s ? "primary" : ""}`}
                    onClick={() => setLeadStatus(current.id, s)}
                  >
                    {STATUS_LABEL[s]}
                  </button>
                ))}
              </span>
            </div>
            <div className="panel-body">
              <dl className="fields">
                <dt>线索编号</dt>
                <dd className="mono">{current.id}</dd>
                <dt>发现方式</dt>
                <dd>{current.foundBy}</dd>
                <dt>观测事实</dt>
                <dd>{current.observed}</dd>
                <dt>证据来源</dt>
                <dd>{current.evidenceSource}</dd>
                <dt>观测时间</dt>
                <dd className="mono">{current.ts.replace("T", " ").replace("Z", "")}</dd>
                <dt>异常原因</dt>
                <dd>{current.reason}</dd>
                <dt>建议下一步</dt>
                <dd>{current.suggestion}</dd>
                <dt>紧急程度</dt>
                <dd><SeverityBadge s={current.severity} /></dd>
                {current.confidence && (
                  <>
                    <dt>涉及置信度</dt>
                    <dd>
                      <ConfBadge c={current.confidence} />{" "}
                      <span style={{ color: "var(--ink-3)", fontSize: 12 }}>
                        （置信度与严重程度独立，{current.confidence} 级候选不会被一键升级为可信资产）
                      </span>
                    </dd>
                  </>
                )}
              </dl>

              {current.relatedAssetKey && (
                <div style={{ marginTop: 14 }}>
                  <button className="btn" onClick={() => openAsset(current.relatedAssetKey!)}>
                    <Icon name="assets" size={14} /> 打开关联资产详情
                  </button>
                </div>
              )}

              <h4 style={{ margin: "18px 0 8px", fontSize: 13 }}>复核备注（本地演示）</h4>
              {leadNotes(current.id).map((n, i) => (
                <div key={i} className="notice info" style={{ alignItems: "flex-start" }}>
                  <Icon name="evidence" size={14} />
                  <div>
                    <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                      {n.author} · <span className="mono">{n.ts.replace("T", " ").slice(0, 19)}</span>
                    </div>
                    {n.text}
                  </div>
                </div>
              ))}
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  type="text"
                  style={{ flex: 1, padding: "7px 10px", border: "1px solid var(--border-strong)", borderRadius: 8 }}
                  placeholder="添加复核备注，例如：已与供应商确认该节点归属…"
                  value={noteDraft}
                  onChange={(e) => setNoteDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && noteDraft.trim()) {
                      addLeadNote(current.id, noteDraft.trim());
                      setNoteDraft("");
                    }
                  }}
                  aria-label="添加备注"
                />
                <button
                  className="btn primary"
                  disabled={!noteDraft.trim()}
                  onClick={() => {
                    addLeadNote(current.id, noteDraft.trim());
                    setNoteDraft("");
                  }}
                >
                  添加
                </button>
              </div>

              <h4 style={{ margin: "18px 0 8px", fontSize: 13 }}>操作历史</h4>
              <div className="timeline">
                {(leadHistory(current.id).length
                  ? leadHistory(current.id)
                  : [{ ts: current.ts, action: "线索生成（后端观测）" }]
                ).map((h, i) => (
                  <div className="tl-item" key={i}>
                    <div className="ts">{h.ts.replace("T", " ").slice(0, 19)}</div>
                    {h.action}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {selectedAsset && <AssetDrawer asset={selectedAsset} onClose={clearSelection} />}
    </div>
  );
}

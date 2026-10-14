import React from "react";
import { useStore } from "../services/store";
import type { ViewKey } from "../types";
import { Icon } from "./Icons";

const NAV: { key: ViewKey; label: string; icon: string }[] = [
  { key: "overview", label: "项目概览", icon: "dashboard" },
  { key: "assets", label: "资产探索", icon: "assets" },
  { key: "tasks", label: "调查任务", icon: "task" },
  { key: "review", label: "证据复核", icon: "evidence" },
  { key: "graph", label: "关系图谱", icon: "graph" },
  { key: "sources", label: "数据来源", icon: "source" },
  { key: "reports", label: "报告中心", icon: "report" },
  { key: "pilot", label: "历史证据", icon: "globe" },
];

export function Sidebar() {
  const { selection, navigate, leads, leadStatus } = useStore();
  const pendingCount = leads.filter((l) => leadStatus(l.id) === "pending").length;

  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>
          <Icon name="eye" size={20} />
          <span className="txt">ASM Workbench</span>
        </h1>
        <div className="sub">暴露面调查工作台</div>
      </div>
      <nav aria-label="主导航">
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-item ${selection.view === n.key ? "active" : ""}`}
            onClick={() => { if (n.key === "pilot") window.location.search = "?pilot=1"; else navigate(n.key); }}
            aria-current={selection.view === n.key ? "page" : undefined}
          >
            <Icon name={n.icon} size={17} />
            <span className="txt">{n.label}</span>
            {n.key === "review" && pendingCount > 0 && (
              <span className="count" aria-label={`${pendingCount} 条待核对`}>
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </nav>
      <div className="env">
        <div className="txt">
          <span className="dot" style={{ background: "#d69e2e" }} />
          演示环境 · 未连接后端
        </div>
        <div className="txt">
          <span className="dot" style={{ background: "#5d7488" }} />
          WSL 执行层：浏览器不可达
        </div>
        <div className="txt" style={{ opacity: 0.7 }}>
          v0.1.0 · 数据采集模式：被动
        </div>
      </div>
    </aside>
  );
}

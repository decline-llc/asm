import React, { useMemo, useRef, useState } from "react";
import { useStore } from "../services/store";
import type { GraphNode, RelationStatus, RelationType } from "../types";
import { Badge, StatusBadge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";
import { AssetDrawer } from "../components/AssetDrawer";

const TYPE_COLOR: Record<GraphNode["type"], string> = {
  company: "#167d8d",
  domain: "#4a90b8",
  ip: "#5d7488",
  service: "#7d5fd3",
  vendor: "#b7791f",
};

const TYPE_LABEL: Record<GraphNode["type"], string> = {
  company: "公司",
  domain: "域名",
  ip: "IP",
  service: "服务",
  vendor: "供应商",
};

const REL_LABEL: Record<RelationType, string> = {
  equity: "股权",
  icp: "备案归属",
  resolves: "解析",
  serves: "服务",
  observed: "页面观测",
  vendor: "供应商线索",
};

/** 确定性分层布局：公司列 → 域名列 → IP 列 → 服务列（供应商置底） */
function layout(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const colX: Record<string, number> = { company: 90, domain: 330, ip: 570, service: 810, vendor: 330 };
  const cols: Record<string, GraphNode[]> = {};
  nodes.forEach((n) => {
    (cols[n.type] ??= []).push(n);
  });
  const pos = new Map<string, { x: number; y: number }>();
  (Object.keys(cols) as GraphNode["type"][]).forEach((type) => {
    const list = cols[type];
    list.forEach((n, i) => {
      const y = type === "vendor" ? 520 : 56 + i * Math.min(78, 460 / Math.max(list.length - 1, 1));
      pos.set(n.id, { x: colX[type], y });
    });
  });
  return pos;
}

export function Graph() {
  const {
    graphNodes, relations, assets, selection, openAsset, clearSelection,
  } = useStore();

  const [fType, setFType] = useState<Set<GraphNode["type"]>>(
    new Set(["company", "domain", "ip", "service", "vendor"])
  );
  const [fRel, setFRel] = useState<Set<RelationStatus>>(new Set(["verified", "candidate", "anomaly"]));
  const [focusId, setFocusId] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);

  const visibleNodes = useMemo(
    () => graphNodes.filter((n) => fType.has(n.type)),
    [graphNodes, fType]
  );
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleRels = relations.filter(
    (r) => fRel.has(r.status) && visibleIds.has(r.from) && visibleIds.has(r.to)
  );
  const pos = useMemo(() => layout(visibleNodes), [visibleNodes]);

  // 从资产详情跳转定位
  React.useEffect(() => {
    if (selection.assetKey) {
      const [host, port] = selection.assetKey.split("|");
      const node = graphNodes.find((n) => n.refId === selection.assetKey);
      if (node) setFocusId(node.id);
    }
  }, [selection.assetKey, graphNodes]);

  const focusNode = focusId ? visibleNodes.find((n) => n.id === focusId) : null;
  const neighborhood = focusId
    ? new Set([
        focusId,
        ...visibleRels.filter((r) => r.from === focusId).map((r) => r.to),
        ...visibleRels.filter((r) => r.to === focusId).map((r) => r.from),
      ])
    : null;

  const toggleType = (t: GraphNode["type"]) => {
    const next = new Set(fType);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    setFType(next);
  };
  const toggleRel = (s: RelationStatus) => {
    const next = new Set(fRel);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    setFRel(next);
  };

  const reset = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
    setFocusId(null);
  };

  const selectedAsset = selection.assetKey
    ? assets.find((a) => `${a.host}|${a.port}|${a.proto}` === selection.assetKey)
    : undefined;

  const onWheel = (e: React.WheelEvent) => {
    const next = Math.min(2.2, Math.max(0.5, scale - Math.sign(e.deltaY) * 0.12));
    setScale(Number(next.toFixed(2)));
  };

  const onMouseDown = (e: React.MouseEvent) => {
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: offset.x, oy: offset.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current) return;
    setOffset({
      x: dragRef.current.ox + (e.clientX - dragRef.current.sx),
      y: dragRef.current.oy + (e.clientY - dragRef.current.sy),
    });
  };
  const onMouseUp = () => (dragRef.current = null);

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>关系图谱</h2>
        <span className="desc">
          局部探索图：点击节点聚焦邻域；实线=已核实，虚线=候选，红色=异常观测
        </span>
      </div>

      <div className="filter-bar panel" style={{ borderRadius: 10, marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>节点类型：</span>
        {(Object.keys(TYPE_LABEL) as GraphNode["type"][]).map((t) => (
          <label key={t} style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 12.5 }}>
            <input type="checkbox" checked={fType.has(t)} onChange={() => toggleType(t)} />
            <span style={{ width: 9, height: 9, borderRadius: 2, background: TYPE_COLOR[t] }} />
            {TYPE_LABEL[t]}
          </label>
        ))}
        <span style={{ fontSize: 12, color: "var(--ink-3)", marginLeft: 12 }}>关系状态：</span>
        {(["verified", "candidate", "anomaly"] as RelationStatus[]).map((s) => (
          <label key={s} style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 12.5 }}>
            <input type="checkbox" checked={fRel.has(s)} onChange={() => toggleRel(s)} />
            <StatusBadge s={s} />
          </label>
        ))}
        <button className="btn small ghost" style={{ marginLeft: "auto" }} onClick={reset}>
          <Icon name="refresh" size={13} /> 重置视图
        </button>
      </div>

      <div className="graph-wrap"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        role="application"
        aria-label="关系图谱（滚轮缩放，拖拽平移，点击节点聚焦）"
      >
        <div className="graph-toolbar">
          <button onClick={() => setScale(Math.min(2.2, scale + 0.15))} aria-label="放大">+</button>
          <button onClick={() => setScale(Math.max(0.5, scale - 0.15))} aria-label="缩小">−</button>
          <button onClick={reset} aria-label="重置" title="重置缩放与聚焦">⌂</button>
        </div>
        <svg width="100%" height="100%" style={{ cursor: dragRef.current ? "grabbing" : "grab" }}>
          <g transform={`translate(${offset.x + 40},${offset.y + 10}) scale(${scale})`}>
            {/* 列标题 */}
            {(["company", "domain", "ip", "service"] as const).map((t) => (
              <text key={t} x={{ company: 90, domain: 330, ip: 570, service: 810 }[t]} y={18}
                textAnchor="middle" fontSize="11" fill="#8ba0b0" fontWeight="600">
                {TYPE_LABEL[t]}
              </text>
            ))}
            {/* 边 */}
            {visibleRels.map((r) => {
              const a = pos.get(r.from);
              const b = pos.get(r.to);
              if (!a || !b) return null;
              const dim = neighborhood && !(neighborhood.has(r.from) && neighborhood.has(r.to));
              const stroke =
                r.status === "anomaly" ? "#c0392b" : r.status === "candidate" ? "#b7791f" : "#7f97a8";
              return (
                <g key={r.id} opacity={dim ? 0.12 : 0.9}>
                  <line
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={stroke}
                    strokeWidth={r.status === "anomaly" ? 2 : 1.4}
                    strokeDasharray={r.status === "candidate" ? "5 4" : r.status === "anomaly" ? "2 3" : undefined}
                  />
                  <text
                    x={(a.x + b.x) / 2}
                    y={(a.y + b.y) / 2 - 4}
                    textAnchor="middle"
                    fontSize="9.5"
                    fill={stroke}
                    style={{ pointerEvents: "none" }}
                  >
                    {r.label}
                  </text>
                </g>
              );
            })}
            {/* 节点 */}
            {visibleNodes.map((n) => {
              const p = pos.get(n.id)!;
              const dim = neighborhood && !neighborhood.has(n.id);
              const focused = focusId === n.id;
              const c = TYPE_COLOR[n.type];
              return (
                <g
                  key={n.id}
                  className="gnode"
                  opacity={dim ? 0.18 : 1}
                  onClick={(e) => {
                    e.stopPropagation();
                    setFocusId(focused ? null : n.id);
                  }}
                  onDoubleClick={() => {
                    if (n.refId && n.refId.includes("|")) openAsset(n.refId);
                  }}
                  role="button"
                  aria-label={`${TYPE_LABEL[n.type]}节点 ${n.label}${n.refId ? "，双击打开详情" : ""}`}
                >
                  <circle cx={p.x} cy={p.y} r={24} fill="transparent" />
                  <circle cx={p.x} cy={p.y} r={focused ? 17 : 13} fill={c} stroke={focused ? "#0f6673" : "#fff"} strokeWidth={focused ? 3 : 2} />
                  <text x={p.x} y={p.y + 28} textAnchor="middle" fontSize="11" fill="#172535" fontWeight={focused ? 700 : 500}>
                    {n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label}
                  </text>
                  {n.sub && (
                    <text x={p.x} y={p.y + 41} textAnchor="middle" fontSize="9" fill="#6b7f8f">
                      {n.sub.length > 20 ? n.sub.slice(0, 19) + "…" : n.sub}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* 节点详情侧卡 */}
      {focusNode && (
        <div className="panel" style={{ marginTop: 12 }}>
          <div className="panel-head">
            <span style={{ width: 10, height: 10, borderRadius: 2, background: TYPE_COLOR[focusNode.type] }} />
            <h3 className="mono" style={{ fontSize: 13.5 }}>{focusNode.label}</h3>
            <Badge tone="neutral">{TYPE_LABEL[focusNode.type]}</Badge>
            {focusNode.sub && <span className="hint">{focusNode.sub}</span>}
          </div>
          <div className="panel-body">
            <h4 style={{ margin: "0 0 8px", fontSize: 12.5 }}>邻域关系（保留证据来源）</h4>
            {visibleRels
              .filter((r) => r.from === focusNode.id || r.to === focusNode.id)
              .map((r) => {
                const other = graphNodes.find((n) => n.id === (r.from === focusNode.id ? r.to : r.from));
                return (
                  <div key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", padding: "5px 0", fontSize: 12.5, flexWrap: "wrap" }}>
                    <Badge tone={r.status === "verified" ? "ok" : r.status === "candidate" ? "warn" : "danger"}>
                      {REL_LABEL[r.type]} · {r.label}
                    </Badge>
                    <span className="mono">{other?.label}</span>
                    <span style={{ color: "var(--ink-3)", fontSize: 11.5 }}>证据：{r.evidence}</span>
                  </div>
                );
              })}
            {focusNode.refId && focusNode.refId.includes("|") && (
              <button className="btn small primary" style={{ marginTop: 8 }} onClick={() => openAsset(focusNode.refId!)}>
                <Icon name="assets" size={13} /> 打开资产详情（表格 / 抽屉联动）
              </button>
            )}
            {focusNode.refId && !focusNode.refId.includes("|") && (
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
                域名节点：可在「资产探索 → 域名」页签查看 DNS 观测详情
              </span>
            )}
            {focusNode.type === "vendor" && (
              <div className="notice warn" style={{ marginTop: 8 }}>
                <Icon name="warn" size={14} />
                供应商线索不意味着供应商资产自动纳入目标范围。
              </div>
            )}
            {focusNode.type === "company" && focusNode.id === "C004" && (
              <div className="notice warn" style={{ marginTop: 8 }}>
                <Icon name="warn" size={14} />
                参股 45%：股权关系不能自动等价于授权范围，归属待人工确认。
              </div>
            )}
          </div>
        </div>
      )}

      <div className="notice info" style={{ marginTop: 12 }}>
        <Icon name="graph" size={14} />
        局部探索设计：默认按 公司 → 域名 → IP → 服务 分层；OSINT 人员信息仅做脱敏演示，不进入图谱。
      </div>

      {selectedAsset && <AssetDrawer asset={selectedAsset} onClose={clearSelection} />}
    </div>
  );
}

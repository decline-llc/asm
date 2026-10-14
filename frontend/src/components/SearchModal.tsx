import React, { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../services/store";
import { assetKey } from "../data/dataset";
import { Icon } from "./Icons";
import { useFocusTrap } from "./useFocusTrap";

interface Hit {
  kind: string;
  label: string;
  sub: string;
  action: () => void;
}

/** 全局搜索：企业 / 域名 / IP / 服务标题 / 任务，键盘可选择跳转 */
export function SearchModal({ onClose }: { onClose: () => void }) {
  const { companies, domains, assets, tasks, navigate, openAsset, openDomain } =
    useStore();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  // 焦点圈定 + Esc + 关闭恢复（Enter 跳转由下方 onKey 处理，preventDefault 防 keyup 合成 click）
  const modalRef = useFocusTrap<HTMLDivElement>({ onClose });

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const hits = useMemo<Hit[]>(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    const out: Hit[] = [];
    for (const c of companies) {
      if (c.name.toLowerCase().includes(s) || c.brand.toLowerCase().includes(s)) {
        out.push({
          kind: "企业",
          label: c.name,
          sub: c.parentCid ? `控股 ${c.sharePct ?? "?"}%` : "种子主体",
          action: () => navigate("graph"),
        });
      }
    }
    for (const d of domains) {
      if (d.domain.includes(s)) {
        out.push({
          kind: "域名",
          label: d.domain,
          sub: `${d.tag5} · 置信度 ${d.confidence}`,
          action: () => openDomain(d.domain),
        });
      }
    }
    const ipSeen = new Set<string>();
    for (const a of assets) {
      if ((a.ip.includes(s) || a.host.includes(s) || a.title.toLowerCase().includes(s)) && out.length < 30) {
        if (a.ip.includes(s) && !ipSeen.has(a.ip)) {
          ipSeen.add(a.ip);
          out.push({
            kind: "IP",
            label: a.ip,
            sub: `被 ${assets.filter((x) => x.ip === a.ip).length} 个资产使用`,
            action: () => openAsset(assetKey(a)),
          });
        }
        if (a.title.toLowerCase().includes(s) || a.host.includes(s)) {
          out.push({
            kind: "服务",
            label: `${a.host}:${a.port}`,
            sub: a.title || a.service,
            action: () => openAsset(assetKey(a)),
          });
        }
      }
    }
    for (const t of tasks) {
      if (t.id.toLowerCase().includes(s) || t.name.toLowerCase().includes(s)) {
        out.push({
          kind: "任务",
          label: t.id,
          sub: t.name,
          action: () => navigate("tasks", { taskId: t.id }),
        });
      }
    }
    return out.slice(0, 20);
  }, [q, companies, domains, assets, tasks, navigate, openAsset, openDomain]);

  useEffect(() => setIdx(0), [q]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") onClose();
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => Math.min(i + 1, hits.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => Math.max(i - 1, 0));
    }
    if (e.key === "Enter" && hits[idx]) {
      // 关键修复：阻止默认行为，避免同一次按键的 keyup 在抽屉刚聚焦的
      // 关闭按钮上合成 click（此前导致「跳转即闪退」）
      e.preventDefault();
      hits[idx].action();
      onClose();
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal search-modal"
        role="dialog"
        aria-label="全局搜索"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="输入企业、域名、IP、服务标题或任务 ID…（↑↓ 选择，Enter 跳转，Esc 关闭）"
          aria-label="搜索关键词"
        />
        <div className="search-results">
          {q && hits.length === 0 && (
            <div className="empty">
              <div className="ico">∅</div>
              无搜索结果：未匹配到企业、域名、IP、服务或任务
            </div>
          )}
          {!q && (
            <div className="empty">
              <Icon name="search" size={26} />
              <div style={{ marginTop: 6 }}>输入关键词开始检索演示数据集</div>
            </div>
          )}
          {hits.map((h, i) => (
            <button
              key={`${h.kind}-${h.label}-${i}`}
              className={`search-hit ${i === idx ? "active" : ""}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => {
                h.action();
                onClose();
              }}
            >
              <span className="kind">{h.kind}</span>
              <span className="label">{h.label}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{h.sub}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

import React from "react";
import { useStore } from "../services/store";

/** 调查面包屑：保留 公司 → 域名 → 服务 → 证据 路径，可回到任意上一级 */
export function Breadcrumb() {
  const { selection, popTrailTo } = useStore();
  if (selection.trail.length <= 1) return null;
  return (
    <nav className="breadcrumb" aria-label="调查路径">
      {selection.trail.map((t, i) => {
        const last = i === selection.trail.length - 1;
        return (
          <React.Fragment key={`${t.label}-${i}`}>
            {i > 0 && <span className="sep">/</span>}
            {last ? (
              <span className="cur" aria-current="page">
                {t.label}
              </span>
            ) : (
              <button onClick={() => popTrailTo(i)}>{t.label}</button>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
}

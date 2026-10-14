import React, { useState } from "react";
import type { ScreenshotState } from "../types";
import { Badge } from "./Badge";
import { Icon } from "./Icons";

/** 演示截图：本地生成的 SVG 页面缩略示意图，明确标注为演示 */
export function Screenshot({
  state,
  host,
  port,
  title,
}: {
  state: ScreenshotState;
  host: string;
  port: number;
  title: string;
}) {
  const [zoom, setZoom] = useState(false);

  if (state.status !== "captured") {
    const map = {
      missing: ["⚠", "截图文件缺失", "warn"],
      failed: ["✕", "截图采集失败", "danger"],
      none: ["—", "未采集截图", "neutral"],
    } as const;
    const [ico, label, tone] = map[state.status];
    return (
      <div className="shot-state">
        <span aria-hidden>{ico}</span>
        <div>
          <Badge tone={tone as "warn" | "danger" | "neutral"}>{label}</Badge>
          <div style={{ marginTop: 4 }}>{state.reason}</div>
        </div>
      </div>
    );
  }

  const hue = Math.abs([...host].reduce((a, c) => a + c.charCodeAt(0), 0)) % 360;
  const svgThumb = (
    <svg viewBox="0 0 400 225" role="img" aria-label={`${host} 页面缩略示意图（演示生成）`}>
      <rect width="400" height="225" fill="#0f1c28" />
      <rect x="0" y="0" width="400" height="26" fill="#1a2d3f" />
      <circle cx="14" cy="13" r="4" fill="#e35d5d" />
      <circle cx="28" cy="13" r="4" fill="#e6b450" />
      <circle cx="42" cy="13" r="4" fill="#4caf7d" />
      <rect x="60" y="7" width="240" height="12" rx="6" fill="#0b141d" />
      <text x="66" y="16" fontSize="8" fill="#7fa3bd" fontFamily="monospace">
        {host}:{port}
      </text>
      <rect x="24" y="44" width="150" height="14" rx="3" fill={`hsl(${hue} 45% 55%)`} />
      <rect x="24" y="66" width="220" height="8" rx="2" fill="#33506b" />
      <rect x="24" y="80" width="180" height="8" rx="2" fill="#2a445c" />
      <rect x="24" y="102" width="70" height="22" rx="4" fill="#167d8d" />
      <rect x="24" y="140" width="100" height="60" rx="4" fill="#16283a" />
      <rect x="136" y="140" width="100" height="60" rx="4" fill="#16283a" />
      <rect x="248" y="140" width="100" height="60" rx="4" fill="#16283a" />
      <text x="24" y="215" fontSize="8" fill="#55748c" fontFamily="monospace">
        demo thumbnail · not a real capture
      </text>
    </svg>
  );

  return (
    <div>
      <div className="shot" style={zoom ? { maxWidth: "100%" } : undefined}>
        {svgThumb}
        <div className="cap">
          <Badge tone="demo">演示生成缩略图</Badge>
          <span className="mono">{state.file}</span>
          <span>{state.ts.replace("T", " ").replace("Z", "")}</span>
          <button className="btn ghost small" style={{ marginLeft: "auto" }} onClick={() => setZoom(!zoom)}>
            <Icon name="eye" size={12} /> {zoom ? "还原" : "放大"}
          </button>
        </div>
      </div>
      {title && <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-3)" }}>页面标题：{title}</div>}
    </div>
  );
}

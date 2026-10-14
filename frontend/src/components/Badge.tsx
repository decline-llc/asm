import React from "react";
import type { Confidence, RelationStatus } from "../types";

export function ConfBadge({ c }: { c: Confidence }) {
  const icons: Record<string, string> = {
    A: "●", B: "●", C: "◐", D: "▲", "D+": "▲", E: "◑", F: "○",
  };
  return (
    <span className={`badge conf-${c}`} title={`置信度 ${c}（与风险严重程度无关）`}>
      <span className="icon">{icons[c]}</span>
      {c}
    </span>
  );
}

export function StatusBadge({ s }: { s: RelationStatus }) {
  const map = {
    verified: ["st-verified", "实线 · 已核实"],
    candidate: ["st-candidate", "虚线 · 候选"],
    anomaly: ["st-anomaly", "异常观测"],
  } as const;
  const [cls, label] = map[s];
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function Badge({
  tone,
  children,
  title,
}: {
  tone: "neutral" | "warn" | "danger" | "ok" | "info" | "demo";
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span className={`badge ${tone}`} title={title}>
      {children}
    </span>
  );
}

export const KIND_LABEL: Record<string, string> = {
  attribution: "归属待核实",
  "dns-conflict": "DNS 冲突",
  "fake-ip": "假地址",
  "dangling-cname": "悬空 CNAME",
  leak: "泄露候选",
  "fuzzy-hit": "模糊命中",
  "collect-fail": "采集失败",
};

export function LeadKindBadge({ kind }: { kind: string }) {
  const tone =
    kind === "fake-ip" || kind === "dns-conflict"
      ? "danger"
      : kind === "collect-fail" || kind === "fuzzy-hit"
        ? "neutral"
        : "warn";
  return <Badge tone={tone as "danger" | "warn" | "neutral"}>{KIND_LABEL[kind] ?? kind}</Badge>;
}

export function SeverityBadge({ s }: { s: "high" | "medium" | "low" }) {
  const map = { high: ["danger", "紧急 · 高"], medium: ["warn", "紧急 · 中"], low: ["neutral", "紧急 · 低"] } as const;
  const [tone, label] = map[s];
  return <Badge tone={tone as "danger" | "warn" | "neutral"}>{label}</Badge>;
}

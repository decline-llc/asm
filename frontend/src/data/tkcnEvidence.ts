// ============================================================
// 被动试点证据载入模块（stub + 本地生成文件回落）。
//
// 设计：真实证据包含目标真实数据（域名/IP/标题），**禁止提交进 git**。
// 证据由 report/tk.cn_delivery/tools/tkcn_build_dataset.py 从
// report/tk.cn_delivery/evidence/ 聚合生成到同目录的
// tkcnEvidence.local.ts（已在 .gitignore 排除）。
// 本文件只包含类型、空数据回落与载入逻辑——可以安全入库。
//
// 复现数据：python report/tk.cn_delivery/tools/tkcn_build_dataset.py
// 缺少 .local 文件时：视图显示「无证据」空态，构建不报错。
// ============================================================

export interface PilotQuery {
  tag: string;
  query: string;
  round: string;
  total: number | null;
  returned: number;
  fpoint: number | null;
  confidence: string;
  ok: boolean;
  why?: string;
  error?: string;
}

export interface PilotDnsUpstream {
  upstream: string;
  answers: string[];
  cnameChain: string[];
  status: string;
}

export interface PilotCandidate {
  host: string;
  ip: string;
  port: number;
  proto: string;
  title: string;
  product: string;
  city: string;
  labels: string[];
  sources: string[];
  queries: string[];
  confidence: "A";
  dns: {
    resolved: boolean;
    ips: string[];
    cnameChain: string[];
    upstreams: PilotDnsUpstream[];
    inconsistent: boolean;
  };
}

export interface PilotNeighbor {
  host: string;
  ip: string;
  port: number;
  title: string;
  product: string;
  kind: "vendor" | "anomaly" | "group" | "ip" | "noise";
  note: string;
  why: string[];
}

export interface PilotDnsObservation {
  domain: string;
  upstreams: PilotDnsUpstream[];
}

export interface PilotSubdomain {
  name: string;
  sources: string[];
}

export interface PilotHighlight {
  host: string;
  note: string;
}

export interface PilotMeta {
  target: string;
  org: string;
  mode: string;
  candidateOnly: boolean;
  stamp: string;
  boundary: string;
  account: string;
  counts: {
    subdomains: number;
    candidates: number;
    dnsResolved: number;
    cdnCname: number;
    inconsistent: number;
    neighbors: number;
    vendors: number;
    anomalies: number;
    ips: number;
    cities: number;
    requests: number;
    fpoints: number;
  };
}

// ---- 载入本地生成证据（不存在时为空对象，构建不报错） ----
const generated = import.meta.glob<{
  TKCN_META: PilotMeta;
  TKCN_QUERIES: PilotQuery[];
  TKCN_CANDIDATES: PilotCandidate[];
  TKCN_NEIGHBORS: PilotNeighbor[];
  TKCN_DNS: PilotDnsObservation[];
  TKCN_SUBDOMAINS: PilotSubdomain[];
  TKCN_HIGHLIGHTS: PilotHighlight[];
  TKCN_RESOLVERS: string[];
  TKCN_SHOT1: string;
  TKCN_SHOT2: string;
}>("./tkcnEvidence.local.ts", { eager: true })["./tkcnEvidence.local.ts"];

/** 是否已载入真实证据（用于空态与导出按钮的禁用） */
export const TKCN_HAS_EVIDENCE = Boolean(generated?.TKCN_META);

export const TKCN_META: PilotMeta =
  generated?.TKCN_META ??
  ({
    target: "",
    org: "（未载入证据）",
    mode: "passive-pilot",
    candidateOnly: true,
    stamp: "",
    boundary:
      "无证据：请先运行 python report/tk.cn_delivery/tools/tkcn_build_dataset.py 从交付目录 evidence/ 聚合生成 tkcnEvidence.local.ts。",
    account: "—",
    counts: {
      subdomains: 0, candidates: 0, dnsResolved: 0, cdnCname: 0, inconsistent: 0,
      neighbors: 0, vendors: 0, anomalies: 0, ips: 0, cities: 0, requests: 0, fpoints: 0,
    },
  } as PilotMeta);

export const TKCN_QUERIES: PilotQuery[] = generated?.TKCN_QUERIES ?? [];
export const TKCN_CANDIDATES: PilotCandidate[] = generated?.TKCN_CANDIDATES ?? [];
export const TKCN_NEIGHBORS: PilotNeighbor[] = generated?.TKCN_NEIGHBORS ?? [];
export const TKCN_DNS: PilotDnsObservation[] = generated?.TKCN_DNS ?? [];
export const TKCN_SUBDOMAINS: PilotSubdomain[] = generated?.TKCN_SUBDOMAINS ?? [];
/** 重点发现（数据驱动；报告模板遍历渲染，前端不硬编码真实资产字符串） */
export const TKCN_HIGHLIGHTS: PilotHighlight[] = generated?.TKCN_HIGHLIGHTS ?? [];
export const TKCN_RESOLVERS: string[] = generated?.TKCN_RESOLVERS ?? [];

/** 表格证据截图（Pillow 本地渲染，base64 内嵌；空字符串 = 无证据） */
export const TKCN_SHOT1: string = generated?.TKCN_SHOT1 ?? "";
export const TKCN_SHOT2: string = generated?.TKCN_SHOT2 ?? "";

// ============================================================
// ASM Workbench 前端类型定义
// 字段语义对齐后端 asm/models.py；标注「演示扩展」的字段
// 当前数据库尚未提供，仅用于演示，未来由适配层替换。
// ============================================================

/** 置信度分级（与风险严重程度无关） */
export type Confidence = "A" | "B" | "C" | "D" | "D+" | "E" | "F";

/** 域名五类标注（资产分类，不是风险评分） */
export type DomainTag =
  | "公开"
  | "有解析未验证"
  | "内网"
  | "独立IP段"
  | "云部署";

/** 关系类型：归属链上的每一种关系都必须标明类型 */
export type RelationType =
  | "equity" // 股权
  | "icp" // 备案归属
  | "resolves" // 解析
  | "serves" // 服务
  | "observed" // 页面观测
  | "vendor"; // 供应商线索

/** 关系证据状态 */
export type RelationStatus = "verified" | "candidate" | "anomaly";

export interface Company {
  cid: string;
  name: string;
  brand: string;
  parentCid: string | null;
  sharePct: number | null; // 股权比例，null 表示未知/不适用
  level: number;
  source: string;
  website: string | null;
  emailSuffix: string | null;
  note: string;
}

export interface DnsObservation {
  upstream: string; // 解析上游，如 223.5.5.5 / 系统默认
  answers: string[];
  ts: string;
  note?: string;
}

export interface DomainRecord {
  domain: string;
  registrable: string;
  cid: string | null;
  tag5: DomainTag;
  confidence: Confidence;
  wildcard: boolean;
  firstSeen: string;
  lastSeen: string;
  sources: string[]; // 多来源命中
  cnameChain: string[]; // CNAME 链（演示扩展）
  dnsObservations: DnsObservation[]; // 多上游观测（演示扩展）
  selectedIps: string[]; // 选用地址
  selectReason: string; // 选用理由
}

export type AssetKind = "service" | "web";

export interface Asset {
  /** 主键语义：host + port + proto */
  host: string;
  ip: string;
  port: number;
  proto: "tcp" | "udp";
  service: string;
  product: string;
  version: string;
  title: string;
  tech: string[];
  cdn: boolean;
  cid: string | null;
  sources: string[];
  confidence: Confidence;
  lastSeen: string;
  kind: AssetKind;
  url?: string;
  labels: string[]; // 如「测试环境」「后台入口」
  screenshot: ScreenshotState; // 演示扩展
  fingerprint?: string; // 服务指纹摘要（演示扩展）
  /** 演示扩展：同一 host|port|proto 解析出的其余地址（CDN 多节点等），主键仍唯一 */
  alternateIps?: string[];
}

export type ScreenshotState =
  | { status: "captured"; file: string; ts: string; demo: true }
  | { status: "missing"; reason: string }
  | { status: "failed"; reason: string }
  | { status: "none"; reason: string };

/** 隔离候选：D 级，永不进入可信资产统计与总表 */
export interface QuarantineCandidate {
  id: string;
  host: string;
  port: number | null;
  proto: string;
  title: string;
  confidence: "D" | "D+";
  source: string;
  reason: string; // 隔离原因，如第三方搜索模糊命中
  observedAt: string;
  evidence: string;
}

export interface Relation {
  id: string;
  from: string; // 节点 id
  to: string;
  type: RelationType;
  status: RelationStatus;
  label: string;
  evidence: string;
}

export interface GraphNode {
  id: string;
  type: "company" | "domain" | "ip" | "service" | "vendor";
  label: string;
  sub?: string;
  refId?: string; // 关联回资产/域名等
}

// ---------------- 证据复核 ----------------

export type LeadKind =
  | "attribution" // 归属待核实
  | "dns-conflict" // DNS 上游冲突
  | "fake-ip" // 假地址观测
  | "dangling-cname" // 悬空 CNAME 候选
  | "leak" // 泄露候选
  | "fuzzy-hit" // 第三方搜索模糊命中
  | "collect-fail"; // 采集失败

export type LeadStatus = "pending" | "reviewed" | "excluded";

export interface ReviewNote {
  ts: string;
  author: string;
  text: string;
}

export interface Lead {
  id: string;
  kind: LeadKind;
  target: string; // 对象（域名/IP/URL）
  foundBy: string; // 发现方式
  observed: string; // 观测事实
  evidenceSource: string; // 证据来源
  ts: string;
  reason: string; // 异常原因
  suggestion: string; // 建议下一步
  severity: "high" | "medium" | "low"; // 紧急程度，与置信度分级无关
  confidence?: Confidence; // 若涉及资产置信度，单独展示
  relatedAssetKey?: string; // host|port|proto
  relatedDomain?: string;
}

// ---------------- 任务 ----------------

export interface StageStep {
  key: string;
  name: string;
  status: "pending" | "running" | "done" | "failed" | "skipped";
  started?: string;
  finished?: string;
  resultCount?: number;
}

export interface SubTask {
  id: string;
  tool: string;
  status: "pending" | "running" | "done" | "failed" | "retrying";
  durationSec?: number;
  resultCount?: number;
  failReason?: string;
  log: string[];
}

export interface InvestigationTask {
  id: string;
  name: string;
  project: string;
  mode: "passive" | "active";
  createdAt: string;
  status: "pending" | "running" | "partial-failed" | "done" | "failed";
  stages: StageStep[];
  subtasks: SubTask[];
  /** 演示扩展：P1/P2 线索轨道为顺序执行，非并发调度 */
  tracks: { key: string; name: string; status: string }[];
}

// ---------------- 数据来源 ----------------

export type SourceCapability =
  | "installed" // 工具已安装
  | "adapter" // 适配器存在
  | "integrated" // 主流程已接入
  | "offline-verified" // 离线已验证
  | "online-verified" // 实网已验证
  | "no-credential"; // 未配置凭据

export interface SourceInfo {
  id: string;
  name: string;
  category: "search-engine" | "tool";
  capabilities: SourceCapability[];
  inMainFlow: boolean;
  demoCalls: number | null; // null = 未运行
  quota: string; // 未知显示「未提供」
  lastError: string | null; // null 与 0 次区分
  resultCount: number | null;
  note: string;
}

// ---------------- 快照（演示扩展） ----------------

export interface Snapshot {
  runId: string;
  finishedAt: string;
  assetKeys: string[]; // host|port|proto
  domainCount: number;
  changedFields: { key: string; field: string; from: string; to: string }[];
  newLeads: number;
}

// ---------------- 报告 ----------------

export type ReportTableKey =
  | "master"
  | "equity"
  | "domains"
  | "ips"
  | "urls"
  | "systems"
  | "social"
  | "todos";

// ---------------- 本地演示状态 ----------------

export interface LocalState {
  leadStatus: Record<string, LeadStatus>;
  leadNotes: Record<string, ReviewNote[]>;
  leadHistory: Record<string, { ts: string; action: string }[]>;
  demoTasks: InvestigationTask[];
  settings: { reduceMotion: boolean };
}

export type ViewKey =
  | "overview"
  | "assets"
  | "tasks"
  | "review"
  | "graph"
  | "sources"
  | "reports"
  | "pilot";

/** 调查面包屑路径节点 */
export interface TrailNode {
  label: string;
  kind: "company" | "domain" | "asset" | "evidence" | "view";
  refId?: string;
}

export interface Selection {
  view: ViewKey;
  assetKey?: string; // host|port|proto
  domain?: string;
  leadId?: string;
  taskId?: string;
  trail: TrailNode[];
}

/** 资产探索筛选状态（提升到 store，跨视图保留；仅会话内存，不持久化） */
export interface AssetFilter {
  tab: "domains" | "ips" | "services" | "web" | "quarantine";
  q: string;
  fCompany: string;
  fSource: string;
  fConf: string;
  fPort: string;
  fCdn: string;
  fLabel: string;
  sortKey: string;
  sortAsc: boolean;
  page: number;
  checked: string[];
}

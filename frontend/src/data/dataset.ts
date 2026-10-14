// ============================================================
// 统一演示数据集（虚构企业「澄川科技集团」）
// - 域名使用 example.com / example.org 子域
// - 公网地址使用文档保留段 192.0.2.0/24、198.51.100.0/24、203.0.113.0/24
// - fake-IP 异常观测使用 198.18.0.0/15（仅作异常观测，不成为资产地址）
// - 快照、历史、DNS 多上游观测等为演示扩展字段
// ============================================================

import type {
  Asset,
  Confidence,
  Company,
  DomainRecord,
  GraphNode,
  InvestigationTask,
  Lead,
  QuarantineCandidate,
  Relation,
  Snapshot,
  SourceInfo,
  StageStep,
} from "../types";

// ---------------- 企业（股权穿透，演示数据） ----------------

export const companies: Company[] = [
  {
    cid: "C001",
    name: "澄川科技集团有限公司",
    brand: "澄川科技",
    parentCid: null,
    sharePct: null,
    level: 0,
    source: "seed",
    website: "https://www.example.com",
    emailSuffix: "example.com",
    note: "种子主体，已纳入授权范围",
  },
  {
    cid: "C002",
    name: "澄川云计算有限公司",
    brand: "澄川云",
    parentCid: "C001",
    sharePct: 85,
    level: 1,
    source: "equity",
    website: "https://cloud.example.com",
    emailSuffix: "cloud.example.com",
    note: "控股 85%，ICP 备案主体一致，已纳入范围",
  },
  {
    cid: "C003",
    name: "澄川智能装备有限公司",
    brand: "澄川智造",
    parentCid: "C001",
    sharePct: 60,
    level: 1,
    source: "equity",
    website: "https://iot.example.com",
    emailSuffix: null,
    note: "控股 60%，已纳入范围",
  },
  {
    cid: "C004",
    name: "澄川数字传媒有限公司",
    brand: "澄川传媒",
    parentCid: "C001",
    sharePct: 45,
    level: 1,
    source: "equity",
    website: null,
    emailSuffix: null,
    note: "参股 45%，股权关系 ≠ 授权范围，归属待人工确认",
  },
  {
    cid: "C005",
    name: "澄川云（杭州）数据中心有限公司",
    brand: "澄川杭州IDC",
    parentCid: "C002",
    sharePct: 100,
    level: 2,
    source: "equity",
    website: null,
    emailSuffix: null,
    note: "澄川云全资子公司，已纳入范围",
  },
];

export const vendors = [
  {
    id: "V001",
    name: "铭安数据服务有限公司",
    role: "CDN/安全防护供应商",
    note: "供应商线索不代表其资产自动纳入目标范围",
  },
  {
    id: "V002",
    name: "云帆科技有限公司",
    role: "SaaS 协同办公供应商（已排除）",
    note: "SaaS 排除项：非目标资产，仅承载业务",
  },
];

// ---------------- 域名 ----------------
// 统一构造，覆盖：多来源命中、CDN、IPv6、DNS 上游冲突、
// fake-IP 异常观测、悬空 CNAME、内网标注、测试环境
// 观测时间全部落在当前运行窗口内（2026-10-09T10:00–10:26Z，run finishedAt 10:26Z 之前）

const T = "2026-10-09T10:";
const obs = (upstream: string, answers: string[], ts: string, note?: string) => ({
  upstream,
  answers,
  ts,
  ...(note ? { note } : {}),
});

export const domains: DomainRecord[] = [
  {
    domain: "www.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "公开",
    confidence: "A",
    wildcard: false,
    firstSeen: "2026-09-28T02:10:00Z",
    lastSeen: `${T}10:20:01Z`,
    sources: ["seed", "FOFA", "Quake", "子域爆破"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["203.0.113.10"], `${T}10:20:11Z`),
      obs("119.29.29.29", ["203.0.113.10"], `${T}10:20:12Z`),
    ],
    selectedIps: ["203.0.113.10"],
    selectReason: "两个上游返回一致 A 记录，直接选用",
  },
  {
    domain: "cloud.example.com",
    registrable: "example.com",
    cid: "C002",
    tag5: "云部署",
    confidence: "A",
    wildcard: false,
    firstSeen: "2026-09-28T02:10:00Z",
    lastSeen: `${T}10:20:03Z`,
    sources: ["seed", "FOFA", "Hunter"],
    cnameChain: ["cloud.example.com.cdn.vendor-dns.example"],
    dnsObservations: [
      obs("223.5.5.5", ["198.51.100.21", "198.51.100.22"], `${T}10:20:15Z`),
      obs("119.29.29.29", ["198.51.100.21", "198.51.100.22"], `${T}10:20:16Z`),
    ],
    selectedIps: ["198.51.100.21", "198.51.100.22"],
    selectReason: "CNAME 至供应商 CDN，双地址一致，标注 CDN 资产",
  },
  {
    domain: "api.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "公开",
    confidence: "A",
    wildcard: false,
    firstSeen: "2026-09-29T06:40:00Z",
    lastSeen: `${T}10:20:05Z`,
    sources: ["FOFA", "Quake", "子域爆破"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["203.0.113.10"], `${T}10:20:20Z`),
      obs("119.29.29.29", ["203.0.113.10"], `${T}10:20:21Z`),
    ],
    selectedIps: ["203.0.113.10"],
    selectReason: "与 www 同址，多来源一致",
  },
  {
    domain: "iot.example.com",
    registrable: "example.com",
    cid: "C003",
    tag5: "独立IP段",
    confidence: "B",
    wildcard: false,
    firstSeen: "2026-09-30T09:12:00Z",
    lastSeen: `${T}10:20:08Z`,
    sources: ["Quake", "子域爆破"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["192.0.2.44"], `${T}10:20:25Z`),
      obs("119.29.29.29", ["192.0.2.44"], `${T}10:20:26Z`),
    ],
    selectedIps: ["192.0.2.44"],
    selectReason: "解析一致，归属 C003 备案主体",
  },
  {
    domain: "dev.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "有解析未验证",
    confidence: "B",
    wildcard: false,
    firstSeen: "2026-10-02T11:03:00Z",
    lastSeen: `${T}10:20:10Z`,
    sources: ["子域爆破", "FOFA"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["203.0.113.40"], `${T}10:20:30Z`),
      obs("119.29.29.29", ["203.0.113.40"], `${T}10:20:31Z`),
    ],
    selectedIps: ["203.0.113.40"],
    selectReason: "命名疑似测试环境，解析一致，标记待核实用途",
  },
  {
    domain: "mail.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "公开",
    confidence: "A",
    wildcard: false,
    firstSeen: "2026-09-28T02:10:00Z",
    lastSeen: `${T}10:20:12Z`,
    sources: ["seed", "FOFA"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["203.0.113.25"], `${T}10:20:35Z`),
      obs("119.29.29.29", ["203.0.113.25"], `${T}10:20:36Z`),
    ],
    selectedIps: ["203.0.113.25"],
    selectReason: "MX 关联主机，双上游一致",
  },
  {
    domain: "vpn.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "公开",
    confidence: "B",
    wildcard: false,
    firstSeen: "2026-10-01T03:20:00Z",
    lastSeen: `${T}10:20:15Z`,
    sources: ["FOFA", "Censys"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["203.0.113.60"], `${T}10:20:40Z`),
      obs("119.29.29.29", ["203.0.113.60"], `${T}10:20:41Z`),
    ],
    selectedIps: ["203.0.113.60"],
    selectReason: "远程入口，解析一致",
  },
  {
    domain: "oa.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "云部署",
    confidence: "C",
    wildcard: false,
    firstSeen: "2026-10-03T08:00:00Z",
    lastSeen: `${T}10:20:18Z`,
    sources: ["Hunter"],
    cnameChain: ["oa.example.com.saas.yunfan.example"],
    dnsObservations: [
      obs("223.5.5.5", ["198.51.100.99"], `${T}10:20:45Z`),
      obs("119.29.29.29", ["198.51.100.99"], `${T}10:20:46Z`),
    ],
    selectedIps: ["198.51.100.99"],
    selectReason: "解析至 SaaS 供应商地址，属排除项范围，仅记录不深入",
  },
  {
    domain: "cdn-static.example.com",
    registrable: "example.com",
    cid: "C002",
    tag5: "云部署",
    confidence: "B",
    wildcard: false,
    firstSeen: "2026-10-02T05:31:00Z",
    lastSeen: `${T}10:20:20Z`,
    sources: ["FOFA", "子域爆破"],
    cnameChain: ["cdn-static.example.com.edgesuite.vendor-dns.example"],
    dnsObservations: [
      obs("223.5.5.5", ["198.51.100.30"], `${T}10:20:50Z`),
      obs("119.29.29.29", ["198.51.100.30"], `${T}10:20:51Z`),
    ],
    selectedIps: ["198.51.100.30"],
    selectReason: "CDN 静态资源域，双上游一致",
  },
  {
    domain: "intranet.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "内网",
    confidence: "C",
    wildcard: false,
    firstSeen: "2026-10-04T10:10:00Z",
    lastSeen: `${T}10:20:22Z`,
    sources: ["证书透明度", "子域爆破"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["10.20.0.8"], `${T}10:20:55Z`, "公网 DNS 返回私网地址"),
      obs("119.29.29.29", ["10.20.0.8"], `${T}10:20:56Z`),
    ],
    selectedIps: ["10.20.0.8"],
    selectReason: "返回私网地址，标注内网，不进入端口扫描",
  },
  {
    domain: "legacy.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "有解析未验证",
    confidence: "C",
    wildcard: false,
    firstSeen: "2026-10-05T01:45:00Z",
    lastSeen: `${T}10:20:25Z`,
    sources: ["子域爆破"],
    cnameChain: ["legacy.example.com.old-host.example"],
    dnsObservations: [
      obs("223.5.5.5", [], `${T}10:21:00Z`, "NXDOMAIN"),
      obs("119.29.29.29", [], `${T}10:21:01Z`, "NXDOMAIN"),
    ],
    selectedIps: [],
    selectReason: "CNAME 目标已不解析，悬空 CNAME 候选，待核对",
  },
  {
    domain: "shop.example.org",
    registrable: "example.org",
    cid: "C004",
    tag5: "有解析未验证",
    confidence: "D+",
    wildcard: false,
    firstSeen: "2026-10-06T07:12:00Z",
    lastSeen: `${T}10:20:28Z`,
    sources: ["Hunter"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["192.0.2.200"], `${T}10:21:05Z`),
      obs("119.29.29.29", ["192.0.2.200"], `${T}10:21:06Z`),
    ],
    selectedIps: ["192.0.2.200"],
    selectReason: "注册商信息相似但无备案交叉证据，归属待核实（C004 参股公司品牌相近）",
  },
  {
    domain: "lab.example.com",
    registrable: "example.com",
    cid: "C001",
    tag5: "有解析未验证",
    confidence: "C",
    wildcard: false,
    firstSeen: "2026-10-06T09:40:00Z",
    lastSeen: `${T}10:20:30Z`,
    sources: ["子域爆破"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["203.0.113.77"], `${T}10:21:10Z`),
      obs("119.29.29.29", ["198.18.0.23"], `${T}10:21:11Z`, "返回 198.18.0.0/15 假地址，疑似上游污染"),
    ],
    selectedIps: ["203.0.113.77"],
    selectReason: "上游冲突：剔除 198.18.0.0/15 假地址，选用 223.5.5.5 观测并挂待核对",
  },
  {
    domain: "v6.example.com",
    registrable: "example.com",
    cid: "C002",
    tag5: "公开",
    confidence: "B",
    wildcard: false,
    firstSeen: "2026-10-07T02:00:00Z",
    lastSeen: `${T}10:20:33Z`,
    sources: ["FOFA", "子域爆破"],
    cnameChain: [],
    dnsObservations: [
      obs("223.5.5.5", ["2001:db8::10", "203.0.113.90"], `${T}10:21:15Z`),
      obs("119.29.29.29", ["2001:db8::10", "203.0.113.90"], `${T}10:21:16Z`),
    ],
    selectedIps: ["2001:db8::10", "203.0.113.90"],
    selectReason: "双栈站点，AAAA 与 A 记录一致",
  },
];

// ---------------- 资产（host + port + proto 为主键） ----------------

const scr = (file: string, ts: string) => ({ status: "captured" as const, file, ts, demo: true as const });

export const assets: Asset[] = [
  {
    host: "www.example.com", ip: "203.0.113.10", port: 443, proto: "tcp",
    service: "https", product: "nginx", version: "1.24.0",
    title: "澄川科技集团 - 官方网站",
    tech: ["nginx", "Vue.js", "HTTP/2"],
    cdn: false, cid: "C001", sources: ["FOFA", "Quake", "httpx"], confidence: "A",
    lastSeen: `${T}10:22:02Z`, kind: "web", url: "https://www.example.com",
    labels: [], fingerprint: "nginx/1.24.0 · TLS1.3 · 证书 CN=www.example.com",
    screenshot: scr("demo-shot-www.png", `${T}10:24:10Z`),
  },
  {
    host: "www.example.com", ip: "203.0.113.10", port: 80, proto: "tcp",
    service: "http", product: "nginx", version: "1.24.0",
    title: "301 → https://www.example.com",
    tech: ["nginx"],
    cdn: false, cid: "C001", sources: ["FOFA", "httpx"], confidence: "A",
    lastSeen: `${T}10:22:04Z`, kind: "web", url: "http://www.example.com",
    labels: [], fingerprint: "nginx/1.24.0 · 301 redirect",
    screenshot: { status: "none", reason: "跳转页未采集截图" },
  },
  {
    host: "api.example.com", ip: "203.0.113.10", port: 443, proto: "tcp",
    service: "https", product: "nginx", version: "1.24.0",
    title: "澄川开放 API 网关",
    tech: ["nginx", "Spring Boot", "Swagger"],
    cdn: false, cid: "C001", sources: ["FOFA", "Quake", "httpx"], confidence: "A",
    lastSeen: `${T}10:22:08Z`, kind: "web", url: "https://api.example.com",
    labels: [], fingerprint: "nginx/1.24.0 · /swagger-ui 200",
    screenshot: scr("demo-shot-api.png", `${T}10:24:22Z`),
  },
  {
    host: "api.example.com", ip: "203.0.113.10", port: 9090, proto: "tcp",
    service: "http", product: "Prometheus", version: "2.47",
    title: "Prometheus - Time Series Collection",
    tech: ["Prometheus", "Go"],
    cdn: false, cid: "C001", sources: ["httpx"], confidence: "B",
    lastSeen: `${T}10:22:15Z`, kind: "web", url: "http://api.example.com:9090",
    labels: ["测试环境"], fingerprint: "Prometheus 2.47 · /graph 200",
    screenshot: { status: "failed", reason: "gowitness 超时 30s，页面持续 loading" },
  },
  {
    host: "cloud.example.com", ip: "198.51.100.21", port: 443, proto: "tcp",
    service: "https", product: "openresty", version: "1.25",
    title: "澄川云控制台",
    tech: ["openresty", "React", "WebSocket"],
    cdn: true, cid: "C002", sources: ["FOFA", "Hunter", "httpx"], confidence: "A",
    lastSeen: `${T}10:22:21Z`, kind: "web", url: "https://cloud.example.com",
    labels: [], fingerprint: "openresty · CDN 节点（铭安数据）",
    screenshot: scr("demo-shot-cloud.png", `${T}10:24:31Z`),
    // 双 A 记录 CDN：第二地址并入同一资产的证据，不重复成行
    // （后端 assets 契约 UNIQUE(host,port,proto)，多来源/多地址不重复计数）
    alternateIps: ["198.51.100.22"],
  },
  {
    host: "iot.example.com", ip: "192.0.2.44", port: 8443, proto: "tcp",
    service: "https", product: "Jetty", version: "9.4",
    title: "澄川智造 - 设备管理平台",
    tech: ["Jetty", "Java", "jQuery"],
    cdn: false, cid: "C003", sources: ["Quake", "httpx"], confidence: "B",
    lastSeen: `${T}10:22:27Z`, kind: "web", url: "https://iot.example.com:8443",
    labels: [], fingerprint: "Jetty 9.4 · 自签证书 CN=iot.example.com",
    screenshot: scr("demo-shot-iot.png", `${T}10:24:40Z`),
  },
  {
    host: "iot.example.com", ip: "192.0.2.44", port: 5683, proto: "udp",
    service: "coap", product: "Californium", version: "",
    title: "",
    tech: ["CoAP"],
    cdn: false, cid: "C003", sources: ["Quake"], confidence: "C",
    lastSeen: `${T}10:22:29Z`, kind: "service",
    labels: [], fingerprint: "CoAP well-known/core 响应",
    screenshot: { status: "none", reason: "非 Web 服务，不采集截图" },
  },
  {
    host: "dev.example.com", ip: "203.0.113.40", port: 8080, proto: "tcp",
    service: "http", product: "Apache Tomcat", version: "9.0",
    title: "澄川测试环境 - Jenkins 构建平台",
    tech: ["Tomcat", "Jenkins", "Java"],
    cdn: false, cid: "C001", sources: ["子域爆破", "httpx", "FOFA"], confidence: "B",
    lastSeen: `${T}10:22:33Z`, kind: "web", url: "http://dev.example.com:8080",
    labels: ["测试环境", "后台入口"], fingerprint: "Tomcat 9.0 · Jenkins 2.4xx 登录页",
    screenshot: scr("demo-shot-dev.png", `${T}10:24:52Z`),
  },
  {
    host: "dev.example.com", ip: "203.0.113.40", port: 22, proto: "tcp",
    service: "ssh", product: "OpenSSH", version: "8.9p1",
    title: "",
    tech: ["OpenSSH"],
    cdn: false, cid: "C001", sources: ["端口扫描"], confidence: "B",
    lastSeen: `${T}10:22:35Z`, kind: "service",
    labels: [], fingerprint: "SSH-2.0-OpenSSH_8.9p1 Ubuntu",
    screenshot: { status: "none", reason: "非 Web 服务，不采集截图" },
  },
  {
    host: "mail.example.com", ip: "203.0.113.25", port: 443, proto: "tcp",
    service: "https", product: "nginx", version: "1.22",
    title: "澄川企业邮箱",
    tech: ["nginx", "Roundcube"],
    cdn: false, cid: "C001", sources: ["FOFA", "httpx"], confidence: "A",
    lastSeen: `${T}10:22:40Z`, kind: "web", url: "https://mail.example.com",
    labels: [], fingerprint: "nginx/1.22 · Roundcube webmail",
    screenshot: scr("demo-shot-mail.png", `${T}10:24:01Z`),
  },
  {
    host: "mail.example.com", ip: "203.0.113.25", port: 25, proto: "tcp",
    service: "smtp", product: "Postfix", version: "",
    title: "",
    tech: ["Postfix"],
    cdn: false, cid: "C001", sources: ["端口扫描"], confidence: "A",
    lastSeen: `${T}10:22:42Z`, kind: "service",
    labels: [], fingerprint: "220 mail.example.com ESMTP Postfix",
    screenshot: { status: "none", reason: "非 Web 服务，不采集截图" },
  },
  {
    host: "vpn.example.com", ip: "203.0.113.60", port: 443, proto: "tcp",
    service: "https", product: "Sangfor SSL VPN", version: "",
    title: "SSL VPN 登录 - 澄川科技",
    tech: ["Sangfor"],
    cdn: false, cid: "C001", sources: ["FOFA", "Censys"], confidence: "B",
    lastSeen: `${T}10:22:46Z`, kind: "web", url: "https://vpn.example.com",
    labels: ["远程入口"], fingerprint: "Sangfor SSL VPN 登录页特征",
    screenshot: { status: "missing", reason: "截图文件缺失：data/shots/vpn.png 不存在" },
  },
  {
    host: "vpn.example.com", ip: "203.0.113.60", port: 4433, proto: "udp",
    service: "ipsec-nat-t", product: "", version: "",
    title: "",
    tech: [],
    cdn: false, cid: "C001", sources: ["端口扫描"], confidence: "C",
    lastSeen: `${T}10:22:48Z`, kind: "service",
    labels: [], fingerprint: "IKEv2 响应",
    screenshot: { status: "none", reason: "非 Web 服务，不采集截图" },
  },
  {
    host: "oa.example.com", ip: "198.51.100.99", port: 443, proto: "tcp",
    service: "https", product: "cloudflare", version: "",
    title: "云帆协同办公 - 登录",
    tech: ["Cloudflare", "SaaS"],
    cdn: true, cid: "C001", sources: ["Hunter"], confidence: "C",
    lastSeen: `${T}10:22:52Z`, kind: "web", url: "https://oa.example.com",
    labels: ["SaaS 排除项"], fingerprint: "SaaS 供应商统一登录页",
    screenshot: { status: "none", reason: "SaaS 排除项，未执行截图" },
  },
  {
    host: "cdn-static.example.com", ip: "198.51.100.30", port: 443, proto: "tcp",
    service: "https", product: "openresty", version: "",
    title: "static assets",
    tech: ["openresty"],
    cdn: true, cid: "C002", sources: ["FOFA", "httpx"], confidence: "B",
    lastSeen: `${T}10:22:55Z`, kind: "web", url: "https://cdn-static.example.com",
    labels: [], fingerprint: "CDN 边缘节点（铭安数据）",
    screenshot: { status: "failed", reason: "目标返回 403，gowitness 标记采集失败" },
  },
  {
    host: "lab.example.com", ip: "203.0.113.77", port: 443, proto: "tcp",
    service: "https", product: "nginx", version: "1.18",
    title: "澄川实验室（内部系统）",
    tech: ["nginx", "Flask"],
    cdn: false, cid: "C001", sources: ["子域爆破", "httpx"], confidence: "C",
    lastSeen: `${T}10:23:00Z`, kind: "web", url: "https://lab.example.com",
    labels: ["测试环境"], fingerprint: "nginx/1.18 · 证书过期 15 天",
    screenshot: scr("demo-shot-lab.png", `${T}10:24:12Z`),
  },
  {
    host: "lab.example.com", ip: "203.0.113.77", port: 9200, proto: "tcp",
    service: "http", product: "Elasticsearch", version: "7.17",
    title: "",
    tech: ["Elasticsearch"],
    cdn: false, cid: "C001", sources: ["httpx"], confidence: "B",
    lastSeen: `${T}10:23:02Z`, kind: "web", url: "http://lab.example.com:9200",
    labels: ["数据服务"], fingerprint: "ES 7.17 · / 返回 cluster JSON",
    screenshot: { status: "none", reason: "JSON 响应，不采集截图" },
  },
  {
    host: "v6.example.com", ip: "2001:db8::10", port: 443, proto: "tcp",
    service: "https", product: "nginx", version: "1.24.0",
    title: "澄川云 IPv6 门户",
    tech: ["nginx", "HTTP/2"],
    cdn: false, cid: "C002", sources: ["FOFA", "httpx"], confidence: "B",
    lastSeen: `${T}10:23:05Z`, kind: "web", url: "https://v6.example.com",
    labels: ["IPv6"], fingerprint: "nginx/1.24.0 · 双栈",
    screenshot: scr("demo-shot-v6.png", `${T}10:24:20Z`),
  },
  {
    host: "shop.example.org", ip: "192.0.2.200", port: 443, proto: "tcp",
    service: "https", product: "nginx", version: "1.20",
    title: "澄川优选商城",
    tech: ["nginx", "PHP"],
    cdn: false, cid: "C004", sources: ["Hunter"], confidence: "D+",
    lastSeen: `${T}10:23:08Z`, kind: "web", url: "https://shop.example.org",
    labels: ["归属待核实"], fingerprint: "nginx/1.20 · 页面含「澄川」品牌词",
    screenshot: { status: "failed", reason: "TLS 握手失败，gowitness 采集失败" },
  },
  {
    // 归属未知（cid=null）且仅 502 观测：按后端 destination() 规则属隔离区，
    // 只能作待核对线索，不能计入可信资产（见线索 L007）
    host: "192.0.2.10", ip: "192.0.2.10", port: 8081, proto: "tcp",
    service: "http", product: "nginx", version: "",
    title: "502 Bad Gateway",
    tech: ["nginx"],
    cdn: false, cid: null, sources: ["端口扫描", "httpx"], confidence: "D",
    lastSeen: `${T}10:23:12Z`, kind: "web", url: "http://192.0.2.10:8081",
    labels: ["待核对"], fingerprint: "nginx · 502 响应，无有效内容指纹",
    screenshot: { status: "none", reason: "502 响应，不采集截图" },
  },
  {
    host: "198.51.100.50", ip: "198.51.100.50", port: 7547, proto: "tcp",
    service: "cwmp", product: "TR-069 ACS", version: "",
    title: "",
    tech: ["CWMP"],
    cdn: false, cid: null, sources: ["Shodan"], confidence: "D+",
    lastSeen: `${T}10:23:15Z`, kind: "service",
    labels: ["归属待核实"], fingerprint: "TR-069 ACS banner，归属未证实",
    screenshot: { status: "none", reason: "非 Web 服务，不采集截图" },
  },
];

// ---------------- 隔离候选（D 级，永不进入可信统计与总表） ----------------

export const quarantine: QuarantineCandidate[] = [
  {
    id: "Q001",
    host: "chengchuan-pay.example",
    port: 443,
    proto: "tcp",
    title: "澄川支付平台（模糊命中）",
    confidence: "D",
    source: "第三方搜索",
    reason: "搜索「澄川」模糊命中，域名与已知根域无注册/备案关联证据",
    observedAt: "2026-10-08T03:11:00Z",
    evidence: "搜索结果页标题含品牌词，无交叉证据；原始快照已留存",
  },
  {
    id: "Q002",
    host: "cc-tech-login.example",
    port: 443,
    proto: "tcp",
    title: "CC Tech Login",
    confidence: "D",
    source: "第三方搜索",
    reason: "品牌缩写相似，注册时间晚于本调查启动，疑似仿冒，隔离待核",
    observedAt: "2026-10-08T03:12:00Z",
    evidence: "WHOIS 隐私保护，无备案；页面 favicon 与官方不一致",
  },
  {
    id: "Q003",
    host: "203.0.113.250",
    port: 8080,
    proto: "tcp",
    title: "澄川内部系统（未验证）",
    confidence: "D+",
    source: "Hunter",
    reason: "页面标题含品牌词，但该地址段无归属记录，不能仅凭标题入册",
    observedAt: "2026-10-08T05:40:00Z",
    evidence: "标题字符串匹配为弱证据；需备案或证书交叉验证",
  },
];

// ---------------- 图谱 ----------------

export const graphNodes: GraphNode[] = [
  { id: "C001", type: "company", label: "澄川科技集团", sub: "种子主体" },
  { id: "C002", type: "company", label: "澄川云计算", sub: "85% 控股" },
  { id: "C003", type: "company", label: "澄川智能装备", sub: "60% 控股" },
  { id: "C004", type: "company", label: "澄川数字传媒", sub: "45% 参股 · 待确认" },
  { id: "C005", type: "company", label: "澄川杭州IDC", sub: "C002 全资" },
  { id: "V001", type: "vendor", label: "铭安数据", sub: "CDN 供应商" },
  { id: "d:www", type: "domain", label: "www.example.com", sub: "公开 · A", refId: "www.example.com" },
  { id: "d:cloud", type: "domain", label: "cloud.example.com", sub: "云部署 · A", refId: "cloud.example.com" },
  { id: "d:api", type: "domain", label: "api.example.com", sub: "公开 · A", refId: "api.example.com" },
  { id: "d:iot", type: "domain", label: "iot.example.com", sub: "独立IP段 · B", refId: "iot.example.com" },
  { id: "d:dev", type: "domain", label: "dev.example.com", sub: "未验证 · B", refId: "dev.example.com" },
  { id: "d:lab", type: "domain", label: "lab.example.com", sub: "未验证 · C · DNS 冲突", refId: "lab.example.com" },
  { id: "d:legacy", type: "domain", label: "legacy.example.com", sub: "悬空 CNAME 候选", refId: "legacy.example.com" },
  { id: "d:shop", type: "domain", label: "shop.example.org", sub: "D+ · 归属待核实", refId: "shop.example.org" },
  { id: "ip:203.0.113.10", type: "ip", label: "203.0.113.10", sub: "官网/API 共址" },
  { id: "ip:198.51.100.21", type: "ip", label: "198.51.100.21", sub: "CDN 节点" },
  { id: "ip:192.0.2.44", type: "ip", label: "192.0.2.44", sub: "IoT 独立段" },
  { id: "ip:203.0.113.40", type: "ip", label: "203.0.113.40", sub: "测试环境" },
  { id: "ip:203.0.113.77", type: "ip", label: "203.0.113.77", sub: "lab 选用地址" },
  { id: "ip:198.18.0.23", type: "ip", label: "198.18.0.23", sub: "fake-IP 异常观测" },
  { id: "s:www443", type: "service", label: "www:443/tcp", sub: "nginx · Vue", refId: "www.example.com|443|tcp" },
  { id: "s:api443", type: "service", label: "api:443/tcp", sub: "API 网关", refId: "api.example.com|443|tcp" },
  { id: "s:api9090", type: "service", label: "api:9090/tcp", sub: "Prometheus", refId: "api.example.com|9090|tcp" },
  { id: "s:iot8443", type: "service", label: "iot:8443/tcp", sub: "Jetty", refId: "iot.example.com|8443|tcp" },
  { id: "s:dev8080", type: "service", label: "dev:8080/tcp", sub: "Jenkins", refId: "dev.example.com|8080|tcp" },
  { id: "s:lab443", type: "service", label: "lab:443/tcp", sub: "nginx · Flask", refId: "lab.example.com|443|tcp" },
];

export const relations: Relation[] = [
  { id: "r1", from: "C001", to: "C002", type: "equity", status: "verified", label: "股权 85%", evidence: "工商股权穿透（演示）" },
  { id: "r2", from: "C001", to: "C003", type: "equity", status: "verified", label: "股权 60%", evidence: "工商股权穿透（演示）" },
  { id: "r3", from: "C001", to: "C004", type: "equity", status: "candidate", label: "股权 45%", evidence: "参股关系存在，授权范围未确认" },
  { id: "r4", from: "C002", to: "C005", type: "equity", status: "verified", label: "股权 100%", evidence: "工商股权穿透（演示）" },
  { id: "r5", from: "C001", to: "d:www", type: "icp", status: "verified", label: "ICP 备案", evidence: "备案主体一致（演示）" },
  { id: "r6", from: "C002", to: "d:cloud", type: "icp", status: "verified", label: "ICP 备案", evidence: "备案主体一致（演示）" },
  { id: "r7", from: "C003", to: "d:iot", type: "icp", status: "verified", label: "ICP 备案", evidence: "备案主体一致（演示）" },
  { id: "r8", from: "C004", to: "d:shop", type: "icp", status: "candidate", label: "品牌相近", evidence: "仅品牌词相似，无备案交叉证据" },
  { id: "r9", from: "d:www", to: "ip:203.0.113.10", type: "resolves", status: "verified", label: "解析", evidence: "双上游一致 A 记录" },
  { id: "r10", from: "d:api", to: "ip:203.0.113.10", type: "resolves", status: "verified", label: "解析", evidence: "双上游一致 A 记录" },
  { id: "r11", from: "d:cloud", to: "ip:198.51.100.21", type: "resolves", status: "verified", label: "解析（CDN）", evidence: "CNAME 至铭安数据 CDN" },
  { id: "r12", from: "d:iot", to: "ip:192.0.2.44", type: "resolves", status: "verified", label: "解析", evidence: "双上游一致" },
  { id: "r13", from: "d:dev", to: "ip:203.0.113.40", type: "resolves", status: "verified", label: "解析", evidence: "双上游一致" },
  { id: "r14", from: "d:lab", to: "ip:203.0.113.77", type: "resolves", status: "verified", label: "解析（选用）", evidence: "剔除假地址后选用" },
  { id: "r15", from: "d:lab", to: "ip:198.18.0.23", type: "resolves", status: "anomaly", label: "异常观测", evidence: "119.29.29.29 返回 198.18.0.0/15 假地址，未采纳" },
  { id: "r16", from: "d:legacy", to: "ip:203.0.113.77", type: "resolves", status: "candidate", label: "悬空 CNAME", evidence: "CNAME 目标 NXDOMAIN，候选关系" },
  { id: "r17", from: "ip:203.0.113.10", to: "s:www443", type: "serves", status: "verified", label: "服务", evidence: "httpx 探测 + 截图" },
  { id: "r18", from: "ip:203.0.113.10", to: "s:api443", type: "serves", status: "verified", label: "服务", evidence: "httpx 探测 + 截图" },
  { id: "r19", from: "ip:203.0.113.10", to: "s:api9090", type: "serves", status: "verified", label: "服务", evidence: "httpx 探测" },
  { id: "r20", from: "ip:192.0.2.44", to: "s:iot8443", type: "serves", status: "verified", label: "服务", evidence: "httpx 探测 + 截图" },
  { id: "r21", from: "ip:203.0.113.40", to: "s:dev8080", type: "serves", status: "verified", label: "服务", evidence: "httpx 探测 + 截图" },
  { id: "r22", from: "ip:203.0.113.77", to: "s:lab443", type: "serves", status: "verified", label: "服务", evidence: "httpx 探测 + 截图" },
  { id: "r23", from: "d:www", to: "s:www443", type: "observed", status: "verified", label: "页面观测", evidence: "标题/证书与品牌一致" },
  { id: "r24", from: "V001", to: "ip:198.51.100.21", type: "vendor", status: "candidate", label: "供应商线索", evidence: "CDN 节点属供应商网络，不纳入目标范围" },
];

// ---------------- 待核对线索 ----------------

export const leads: Lead[] = [
  {
    id: "L001", kind: "dns-conflict", target: "lab.example.com",
    foundBy: "DNS 多上游复核（dnsx/dig）",
    observed: "223.5.5.5 返回 203.0.113.77；119.29.29.29 返回 198.18.0.23（198.18.0.0/15）",
    evidenceSource: "Stage DNS · 上游观测日志",
    ts: `${T}10:21:11Z`,
    reason: "上游返回假地址（fake-IP），属异常观测",
    suggestion: "以加密上游（DoH）复核解析路径；确认 203.0.113.77 为真实服务地址",
    severity: "high", confidence: "C", relatedDomain: "lab.example.com",
    relatedAssetKey: "lab.example.com|443|tcp",
  },
  {
    id: "L002", kind: "fake-ip", target: "198.18.0.23",
    foundBy: "DNS 异常观测规则",
    observed: "198.18.0.0/15 为基准测试保留段，公网 DNS 不应返回",
    evidenceSource: "Stage DNS · 观测比对",
    ts: `${T}10:21:12Z`,
    reason: "假地址仅作异常观测记录，不成为可扫描资产地址",
    suggestion: "排查出口链路 DNS 劫持/污染；复测上游",
    severity: "high",
  },
  {
    id: "L003", kind: "attribution", target: "shop.example.org",
    foundBy: "Hunter 品牌词搜索",
    observed: "页面标题含「澄川」，注册商信息相近，无备案交叉证据",
    evidenceSource: "Hunter 结果快照",
    ts: "2026-10-08T03:15:00Z",
    reason: "C004（参股 45%）品牌相近，但股权关系 ≠ 授权范围",
    suggestion: "人工确认 C004 是否在授权范围；补充备案/证书证据",
    severity: "medium", confidence: "D+", relatedDomain: "shop.example.org",
    relatedAssetKey: "shop.example.org|443|tcp",
  },
  {
    id: "L004", kind: "dangling-cname", target: "legacy.example.com",
    foundBy: "CNAME 链追踪",
    observed: "CNAME → legacy.example.com.old-host.example，目标 NXDOMAIN",
    evidenceSource: "Stage DNS · CNAME 链",
    ts: `${T}10:21:01Z`,
    reason: "悬空 CNAME 候选，存在接管风险（仅线索，不直接定级）",
    suggestion: "核对旧托管商状态；确认是否已释放该域名",
    severity: "medium", relatedDomain: "legacy.example.com",
  },
  {
    id: "L005", kind: "collect-fail", target: "https://cdn-static.example.com",
    foundBy: "gowitness 截图",
    observed: "目标返回 403，截图采集失败",
    evidenceSource: "Stage Web · gowitness 日志",
    ts: `${T}10:24:05Z`,
    reason: "CDN 边缘节点拒绝默认 UA/无 Referer 请求",
    suggestion: "携带浏览器指纹重试；或标记 CDN 节点免截图",
    severity: "low", relatedAssetKey: "cdn-static.example.com|443|tcp",
  },
  {
    id: "L006", kind: "collect-fail", target: "http://api.example.com:9090",
    foundBy: "gowitness 截图",
    observed: "页面持续 loading，30s 超时",
    evidenceSource: "Stage Web · gowitness 日志",
    ts: `${T}10:24:30Z`,
    reason: "Prometheus 页面异步渲染超时",
    suggestion: "延长超时或改用 API 探测；确认该端口是否应暴露",
    severity: "medium", relatedAssetKey: "api.example.com|9090|tcp",
  },
  {
    id: "L007", kind: "attribution", target: "192.0.2.10:8081",
    foundBy: "端口扫描 + httpx",
    observed: "502 Bad Gateway，无有效指纹，归属未知",
    evidenceSource: "Stage 端口 · httpx 输出",
    ts: `${T}10:23:12Z`,
    reason: "502 响应只能作为待核对线索，不能定级",
    suggestion: "周期复测；比对证书透明度日志",
    severity: "medium", confidence: "C", relatedAssetKey: "192.0.2.10|8081|tcp",
  },
  {
    id: "L008", kind: "fuzzy-hit", target: "chengchuan-pay.example",
    foundBy: "第三方搜索（品牌词）",
    observed: "标题含品牌词，无注册/备案关联",
    evidenceSource: "搜索结果快照",
    ts: "2026-10-08T03:11:00Z",
    reason: "D 级模糊命中，已入隔离区，永不进入可信统计",
    suggestion: "保持隔离；如确认仿冒，转威胁处置流程",
    severity: "low", confidence: "D",
  },
  {
    id: "L009", kind: "leak", target: "git 仓库快照（演示）",
    foundBy: "P1 OSINT 线索",
    observed: "公开代码片段疑似包含内网域名 test.intra.example.com",
    evidenceSource: "OSINT 线索记录（脱敏演示）",
    ts: "2026-10-07T10:20:00Z",
    reason: "泄露候选，需人工确认真实性与影响面",
    suggestion: "核对仓库归属与提交时间；确认是否真实敏感信息",
    severity: "medium",
  },
  {
    id: "L010", kind: "attribution", target: "198.51.100.50:7547",
    foundBy: "Shodan 结果",
    observed: "TR-069 ACS banner，地址段无归属记录",
    evidenceSource: "Shodan 结果（适配器演示）",
    ts: `${T}10:23:15Z`,
    reason: "D+ 级，归属未证实，不能仅凭 banner 入册",
    suggestion: "反查该段 WHOIS；与供应商确认设备归属",
    severity: "low", confidence: "D+", relatedAssetKey: "198.51.100.50|7547|tcp",
  },
  {
    id: "L011", kind: "attribution", target: "澄川数字传媒有限公司",
    foundBy: "股权穿透",
    observed: "C001 参股 45%，未提供针对该公司的授权",
    evidenceSource: "Stage 2a/2b · 股权穿透结果",
    ts: "2026-10-09T01:00:00Z",
    reason: "股权关系不能自动等价于授权范围",
    suggestion: "与客户确认 C004 及其资产是否纳入调查范围",
    severity: "high",
  },
  {
    id: "L012", kind: "collect-fail", target: "https://vpn.example.com",
    foundBy: "gowitness 截图",
    observed: "截图文件缺失：data/shots/vpn.png 不存在",
    evidenceSource: "Stage Web · 文件清点",
    ts: `${T}10:24:30Z`,
    reason: "采集流程中断或文件被清理",
    suggestion: "重跑截图子任务；核对结果目录权限",
    severity: "low", relatedAssetKey: "vpn.example.com|443|tcp",
  },
];

// ---------------- 任务（8–12 个） ----------------

// 子任务工具名按演示运行的默认引擎展示（docs/OPERATIONS.md 与 profiles/modes.yaml）：
// 子域=OneForAll、DNS=dnsx/dig、端口=nmap（Stage 6 默认引擎）、Web 探测=httpx(Windows)、
// 截图=Playwright(Windows)（后两者为 Stage 7 默认引擎）。
// naabu/a_scan、WSL httpx、katana、ffuf、gowitness、nuclei、wafw00f 已作为可选引擎接入，
// 但需在计划中显式选中，本轮演示未调用，故不作为执行工具展示（来源页以「已接入」徽章体现）。

const mkStages = (upto: number, failedAt = -1): StageStep[] => {
  const names: [string, string][] = [
    ["s1", "种子标准化"], ["s2", "股权穿透与ICP备案"], ["s3", "范围确认"],
    ["s4", "子域名收集"], ["s5", "DNS/CDN 分析"], ["s6", "端口服务发现"],
    ["s7", "Web 识别与截图"], ["s8", "报告生成"],
  ];
  const base = Date.parse("2026-10-09T10:00:00Z");
  return names.map(([key, name], i): StageStep => {
    const status = i === failedAt ? "failed" : failedAt >= 0 && i > failedAt ? "pending"
      : i < upto ? "done" : i === upto ? "running" : "pending";
    return {
      key, name, status,
      started: status !== "pending" ? new Date(base + i * 60_000).toISOString() : undefined,
      finished: status === "done" ? new Date(base + i * 60_000 + ((i * 7) % 60) * 1000).toISOString() : undefined,
      resultCount: status === "done" ? [5, 6, 1, 34, 30, 22, 17, 1][i] : undefined,
    };
  });
};

export const tasks: InvestigationTask[] = [
  {
    id: "RUN-20261009-01",
    name: "澄川科技集团 · 被动基线",
    project: "澄川科技集团",
    mode: "passive",
    createdAt: "2026-10-09T10:00:00Z",
    status: "partial-failed",
    // s7 Web 识别与截图失败（对应截图子任务），s8 报告等待重试后生成
    stages: mkStages(7, 6),
    subtasks: [
      { id: "st1", tool: "oneforall", status: "done", durationSec: 412, resultCount: 34, log: ["[10:04] OneForAll 七来源白名单采集（默认五来源）", "[10:11] 合并 34 个候选子域", "[10:11] 来源失败证据：Zoomeye API 超时（已记录）"] },
      { id: "st2", tool: "dnsx/dig", status: "done", durationSec: 180, resultCount: 30, log: ["[10:12] 多上游解析：223.5.5.5 / 119.29.29.29", "[10:15] 发现 1 条上游冲突（lab.example.com）", "[10:15] 198.18.0.23 标记为假地址观测"] },
      { id: "st3", tool: "nmap", status: "done", durationSec: 260, resultCount: 22, log: ["[10:16] nmap 对 12 个选用地址执行端口扫描", "[10:20] 22 个开放端口入库"] },
      { id: "st4", tool: "httpx (Windows)", status: "done", durationSec: 140, resultCount: 17, log: ["[10:21] Web 探测 17 个存活", "[10:23] 192.0.2.10:8081 返回 502，标记待核对"] },
      { id: "st5", tool: "playwright-截图", status: "failed", durationSec: 95, failReason: "3 个目标截图失败（403/超时/TLS）", log: ["[10:24] 开始截图 17 个目标（Windows Playwright）", "[10:26] 完成 13 个；失败 3 个；缺失 1 个", "[10:26] 失败明细已写入证据复核队列"] },
      { id: "st6", tool: "report", status: "pending", log: ["等待重试截图后生成"] },
    ],
    tracks: [
      { key: "main", name: "主流程（顺序执行）", status: "Stage 7 部分失败，待重试" },
      { key: "p1", name: "P1 OSINT 线索", status: "已完成（顺序轨道）" },
      { key: "p2", name: "P2 供应链线索", status: "已完成（顺序轨道）" },
    ],
  },
  {
    id: "RUN-20261002-01",
    name: "澄川科技集团 · 首次被动采集",
    project: "澄川科技集团",
    mode: "passive",
    createdAt: "2026-10-02T09:30:00Z",
    status: "done",
    stages: mkStages(8),
    subtasks: [
      { id: "st1", tool: "oneforall", status: "done", durationSec: 388, resultCount: 28, log: ["[09:36] 合并 28 个候选子域"] },
      { id: "st2", tool: "dnsx/dig", status: "done", durationSec: 160, resultCount: 24, log: ["[09:40] 多上游解析完成"] },
      { id: "st3", tool: "httpx (Windows)", status: "done", durationSec: 120, resultCount: 14, log: ["[09:45] Web 探测 14 个存活"] },
      { id: "st4", tool: "playwright-截图", status: "done", durationSec: 110, resultCount: 14, log: ["[09:48] 截图 14/14（Windows Playwright）"] },
      { id: "st5", tool: "report", status: "done", durationSec: 12, resultCount: 1, log: ["[09:50] 报告已生成（xlsx/csv/html）"] },
    ],
    tracks: [
      { key: "main", name: "主流程（顺序执行）", status: "已完成" },
      { key: "p1", name: "P1 OSINT 线索", status: "未启用" },
      { key: "p2", name: "P2 供应链线索", status: "未启用" },
    ],
  },
];

// ---------------- 快照（演示扩展） ----------------
// assetKeys 只存合法的可信资产主键（host|port|proto）；D/D+ 隔离候选另行计数。
// 观测/发现时间均落在各自运行窗口内（10-02 运行 09:30–09:50，10-09 运行 10:00–10:26）。

export const snapshots: Snapshot[] = [
  {
    runId: "RUN-20261002-01",
    finishedAt: "2026-10-02T09:50:00Z",
    assetKeys: [
      "www.example.com|443|tcp", "www.example.com|80|tcp", "api.example.com|443|tcp",
      "cloud.example.com|443|tcp", "iot.example.com|8443|tcp", "mail.example.com|443|tcp",
      "mail.example.com|25|tcp", "vpn.example.com|443|tcp", "dev.example.com|8080|tcp",
      "dev.example.com|22|tcp", "cdn-static.example.com|443|tcp", "v6.example.com|443|tcp",
      "lab.example.com|443|tcp", "oa.example.com|443|tcp",
    ],
    domainCount: 12,
    changedFields: [],
    newLeads: 0,
  },
  {
    runId: "RUN-20261009-01",
    finishedAt: "2026-10-09T10:26:00Z",
    // 与当前可信资产集合（15 项）一一对应；D/D+ 不进入快照口径
    assetKeys: [
      "www.example.com|443|tcp", "www.example.com|80|tcp", "api.example.com|443|tcp",
      "api.example.com|9090|tcp", "cloud.example.com|443|tcp",
      "iot.example.com|8443|tcp", "mail.example.com|443|tcp",
      "mail.example.com|25|tcp", "vpn.example.com|443|tcp",
      "dev.example.com|8080|tcp", "dev.example.com|22|tcp", "cdn-static.example.com|443|tcp",
      "v6.example.com|443|tcp", "lab.example.com|443|tcp", "lab.example.com|9200|tcp",
    ],
    domainCount: 14,
    changedFields: [
      { key: "www.example.com|443|tcp", field: "tech", from: "nginx", to: "nginx, Vue.js, HTTP/2" },
      { key: "iot.example.com|8443|tcp", field: "title", from: "设备平台", to: "澄川智造 - 设备管理平台" },
      { key: "vpn.example.com|443|tcp", field: "screenshot", from: "captured", to: "missing" },
    ],
    // 10-09 观测的线索共 9 条（L001/L002/L004–L007/L010/L012 + lab:9200）
    newLeads: 9,
  },
];

// ---------------- 数据来源 ----------------
// 能力状态按后端事实对齐，权威来源：
// - 版本与集成状态矩阵：docs/reference/tool-versions.md（Session 010，与 tools/tool-lock.json 由测试强制一致）
// - 调度与默认引擎：docs/OPERATIONS.md 工具表、profiles/modes.yaml
// - 隔离 broker 范围契约：docs/TOOL_INTEGRATION.md（Session 009，tests/unit/test_broker_scope.py 固定）
//
// 徽章语义（7 级，不互相替代）：
//   installed 已安装 / adapter 适配器存在 / integrated 已完成代码接入（含需显式选中的可选引擎）/
//   offline-verified 离线或回环已验证 / online-verified 实网已验证 / no-credential 未配置凭据 /
//   runtime-dependency 仅被其它工具调用，不独立调度
// inMainFlow 只表示「当前主流程会默认自动调度」（默认引擎/默认来源）。可选引擎已 integrated
// 但需在计划中显式选中，故 inMainFlow=false —— 接入徽章与主流程徽章各说一件事，不再混用。
//   默认引擎：Stage 4 = subfinder + OneForAll；Stage 5 = dnsx/dig；Stage 6 = nmap；
//   Stage 7 = Web 探测 httpx(Windows)、截图 Playwright、爬取 native_crawler、
//   路径 stage_7_paths、风险核查 native_risk_checks。
//   可选引擎（Stage 6/7）：naabu、a_scan、httpx(WSL)、katana、ffuf、gowitness、nuclei、wafw00f。
// 凭据事实：本机 .env 仅 FOFA_EMAIL/FOFA_KEY 已配置，且已完成一次受控被动试点
//   （2026-10-10，11 次请求 / 0 F 点 / 限速 ≥20s，证据 report/tk.cn_delivery/）；其余五家为空。
//   真实账户的泛化验收仍未执行，故任何来源都不标 online-verified。
// DNS 事实：Session 008 已实施 DoH 可信解析路径（RFC 8484，可选、仓库内 profile 一律不默认开启），
//   假地址（198.18.0.0/15）与回环答案会被拒绝；本机系统解析仍被劫持。
// 演示计数：本轮演示按默认引擎执行；未调用的可选引擎 demoCalls=null，页面显示「未运行」
//   （与「失败」「无错误」分开呈现，不伪装成已执行）。

export const sources: SourceInfo[] = [
  { id: "fofa", name: "FOFA", category: "search-engine", capabilities: ["installed", "adapter", "integrated", "offline-verified"], inMainFlow: true, demoCalls: 6, quota: "未提供", lastError: null, resultCount: 14, note: "主流程自动查询来源之一；凭据已配置并完成一次受控被动试点（2026-10-10，11 次请求 / 0 F 点 / 限速 ≥20s）；本卡计数为演示回放，真实账户泛化验收待执行，故不标「实网已验证」" },
  { id: "quake", name: "Quake", category: "search-engine", capabilities: ["installed", "adapter", "integrated", "offline-verified", "no-credential"], inMainFlow: true, demoCalls: 4, quota: "未提供", lastError: null, resultCount: 9, note: "主流程自动查询来源之一；凭据未配置，实网验证待执行" },
  { id: "hunter", name: "Hunter", category: "search-engine", capabilities: ["adapter", "no-credential"], inMainFlow: false, demoCalls: 2, quota: "未配置凭据", lastError: null, resultCount: 4, note: "适配器存在，未接入主调度；演示调用为手工触发" },
  { id: "zoomeye", name: "ZoomEye", category: "search-engine", capabilities: ["adapter", "no-credential"], inMainFlow: false, demoCalls: null, quota: "未配置凭据", lastError: "API 超时（10-09 10:11，OneForAll 渠道）", resultCount: null, note: "未运行≠失败：本轮经 OneForAll 渠道尝试超时" },
  { id: "shodan", name: "Shodan", category: "search-engine", capabilities: ["adapter", "no-credential"], inMainFlow: false, demoCalls: 1, quota: "未配置凭据", lastError: null, resultCount: 1, note: "适配器存在，演示调用 1 次" },
  { id: "censys", name: "Censys", category: "search-engine", capabilities: ["adapter", "no-credential"], inMainFlow: false, demoCalls: 1, quota: "未提供", lastError: null, resultCount: 1, note: "适配器存在（Legacy v2），未接入主调度；Platform v3/PAT 迁移待做" },
  { id: "subfinder", name: "subfinder（被动子域）", category: "tool", capabilities: ["installed", "integrated"], inMainFlow: true, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 4 自动调用（幂等缓存），与 OneForAll、公开来源并行；提供商凭据在 WSL ~/.config/subfinder/provider-config.yaml，与 Windows .env 不互通；本轮演示未单列其计数" },
  { id: "oneforall", name: "OneForAll（子域）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: true, demoCalls: 2, quota: "—", lastError: null, resultCount: 34, note: "WSL 内运行，Stage 4 隔离被动调用，七来源白名单（默认五）" },
  { id: "dnsx", name: "dnsx / dig（DNS）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: true, demoCalls: 2, quota: "—", lastError: null, resultCount: 30, note: "Stage 5 自动调用，多上游复核；可信解析路径已实施（可选 RFC 8484 DoH 加密上游，假地址与回环答案拒绝），仓库内 profile 不默认开启 DoH，本机系统解析仍被劫持" },
  { id: "nmap", name: "nmap（端口扫描）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: true, demoCalls: 1, quota: "—", lastError: null, resultCount: 22, note: "Stage 6 默认引擎（WSL），回环 TCP/UDP 已验收" },
  { id: "naabu", name: "naabu（端口发现）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 6 端口发现可选引擎（经适配器）；候选端口逐条校验目标一致后由 nmap 确认服务；本轮演示 Stage 6 由默认引擎 nmap 执行" },
  { id: "a_scan", name: "a_scan（端口发现）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 6 端口发现可选引擎（项目 stdlib TCP 工具，任务内副本 + 哈希校验）；只给 TCP connect 候选，不做服务版本识别；本轮演示未调用" },
  { id: "httpx-win", name: "httpx（Windows · Web 探测）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: true, demoCalls: 2, quota: "—", lastError: null, resultCount: 17, note: "Stage 7 默认 Web 探测（Windows Python httpx，非 WSL 版）" },
  { id: "httpx-wsl", name: "httpx（WSL · 隔离 broker）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 7 web_visit 可选引擎（ProjectDiscovery httpx）；在仅 loopback 的私有 network namespace 内运行，每个 GET/HEAD 经 broker 交回范围/预算/回执，越界主机 403 且零传输；本轮演示由 Windows 侧探测承担" },
  { id: "katana", name: "katana（爬取 · JS 端点）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 7 web_crawl 可选引擎（隔离 broker）；精确 crawl-scope + -dr/-duc，JS 端点提取 -jc 默认开启（tool_options.katana.js_crawl: false 可关），jsluice 显式拒绝；broker 未实际请求的 URL 降级为范围外线索；本轮演示未调用" },
  { id: "ffuf", name: "ffuf（路径枚举）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 7 web_path_enum 可选引擎（隔离 broker，随机基线 + 二次 HTTP 复核，排除统一返回页）；本轮演示未调用" },
  { id: "playwright", name: "Playwright（Windows · 截图）", category: "tool", capabilities: ["installed", "integrated"], inMainFlow: true, demoCalls: 2, quota: "—", lastError: "3 个目标失败（403/超时/TLS）", resultCount: 13, note: "Stage 7 默认截图引擎（Windows Playwright，每个浏览器请求经范围复核）；部分失败可重试" },
  { id: "gowitness", name: "gowitness（截图 · 隔离 broker）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 7 screenshot 可选引擎（gorod 驱动 + 任务内 Chrome 代理，Chrome 只信任本任务代理证书的固定 SPKI）；无 PNG 或失败按 partial，不算完成；本轮演示截图由默认引擎 Playwright 承担" },
  { id: "nuclei", name: "nuclei（模板核查）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 7 vulnerability_check 可选；仅执行仓库内已批准的 HTTP 观察模板，模板命中是待复核线索而非已确认漏洞；本轮演示未调用" },
  { id: "wafw00f", name: "wafw00f（WAF 指纹）", category: "tool", capabilities: ["installed", "integrated", "offline-verified"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "Stage 7 vulnerability_check 可选，须显式选中 waf_fingerprint；指纹只作复核候选，不作归属或漏洞依据；独立 venv、未在 tool-lock 固定；本轮演示未调用" },
  { id: "chrome", name: "Chrome（gowitness 运行时依赖）", category: "tool", capabilities: ["installed", "runtime-dependency"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "仅由 gowitness 以固定 SPKI 代理启动，不独立调度；本轮演示未使用 gowitness，故未启动" },
  { id: "seclists", name: "SecLists（字典输入）", category: "tool", capabilities: ["installed", "runtime-dependency"], inMainFlow: false, demoCalls: null, quota: "—", lastError: null, resultCount: null, note: "固定 commit 稀疏检出的 7 个字典文件，作为 DNS/内置路径/ffuf 的冻结输入（非采集结果）；Stage 4 当前使用内置 DNS_PREFIXES，不自动读全部 SecLists" },
];

// ---------------- 统计口径（镜像后端 asm/precision.py destination()） ----------------
// 后端规则：A/B → assets；C 需 ≥2 独立来源或三重归属佐证才升入（升为 A）；
// D+ 仅「中小企业已验证例外」可入 assets（前端演示不自动判定该例外）；
// 其余（含 D、E、F）一律 assets_quarantine，永不进入可信统计与总表。

/** 与后端 destination() 对齐的可信判定 */
export function isTrustedConfidence(confidence: Confidence, sources: readonly string[] = []): boolean {
  if (confidence === "A" || confidence === "B") return true;
  // C 级：需 ≥2 独立来源佐证，否则视为隔离展示
  if (confidence === "C") return new Set(sources).size >= 2;
  return false; // D / D+ / E / F → 隔离区
}

export function isTrustedAsset(a: Asset): boolean {
  return isTrustedConfidence(a.confidence, a.sources);
}

export function assetKey(a: { host: string; port: number; proto: string }) {
  return `${a.host}|${a.port}|${a.proto}`;
}

/** 隔离展示（含 D/D+，及未达佐证条件的单来源 C）；永不进入可信统计与总表 */
export function quarantinedAssets(list: Asset[]) {
  return list.filter((a) => !isTrustedAsset(a));
}

/** 可信资产按 host+port+proto 去重；D/D+（与未佐证 C）永不计入 */
export function trustedAssets(list: Asset[]) {
  const seen = new Map<string, Asset>();
  for (const a of list) {
    if (!isTrustedAsset(a)) continue;
    seen.set(assetKey(a), a);
  }
  return [...seen.values()];
}

/** 快照差分：新增与离开可信集均保留，不将离开误称为资产已消失。 */
export function diffNewAssetKeys(snaps: Snapshot[]): { added: string[]; removed: string[] } {
  if (snaps.length < 2) return { added: [], removed: [] };
  const [prev, cur] = snaps;
  const prevSet = new Set(prev.assetKeys);
  const curSet = new Set(cur.assetKeys);
  return { added: [...curSet].filter((k) => !prevSet.has(k)), removed: [...prevSet].filter((k) => !curSet.has(k)) };
}

/** 198.18.0.0/15 基准测试保留段（fake-IP 异常观测段；按整数网段判断，不误伤相邻公网段） */
export function isFakeIp(ip: string): boolean {
  const parts = ip.split(".");
  if (parts.length !== 4) return false;
  const nums = parts.map((p) => Number(p));
  if (nums.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return false;
  // 198.18.0.0/15 = 198.18.x.x – 198.19.x.x
  return nums[0] === 198 && (nums[1] === 18 || nums[1] === 19);
}

export const projectMeta = {
  name: "澄川科技集团",
  seeds: { companies: 1, rootDomains: ["example.com"], ipRanges: ["203.0.113.0/25（演示段）"] },
  mode: "passive" as const,
  currentRun: "RUN-20261009-01",
  lastRunAt: "2026-10-09T10:26:00Z",
  exclusions: ["云帆 SaaS（非目标资产）", "198.18.0.0/15 假地址观测段"],
  stages: [
    "种子输入", "股权穿透 / ICP 备案", "范围确认", "子域收集",
    "DNS/CDN 分析", "端口服务", "Web 识别", "报告",
  ],
};

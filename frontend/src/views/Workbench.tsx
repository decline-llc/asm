import React, { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, subscribeRun, workbenchApi, type Artifact, type JsonObject, type ModeCatalog, type ProjectRecord, type RunEvent, type RunRecord } from "../services/workbenchApi";
import "../workbench.css";
import { ProjectCenter } from "../components/ProjectCenter";

const LABELS: Record<string, string> = {
  search: "公开资产搜索", company_lookup: "主体与备案", passive_subdomains: "被动子域发现", osint: "公开情报",
  passive_supply_chain: "供应链关联", dns_recursive: "DNS 观测", tcp_scan: "TCP 端口", service_probe: "服务核实",
  web_visit: "网页访问", tls_inspect: "TLS 与证书", screenshot: "网页截图", dns_enum: "DNS 枚举", udp_scan: "UDP 端口",
  deep_service_probe: "深入服务探测", web_crawl: "网页爬取", js_analysis: "JS 线索", web_path_enum: "路径枚举",
  exposure_check: "暴露核查", vulnerability_check: "风险核查", takeover_probe: "接管候选核查", auth_audit: "专项认证核查",
  evidence_normalize: "证据归一", ownership_review: "归属复核", coverage_summary: "覆盖汇总", dual_reports: "双版本交付",
};
const STATE_LABELS: Record<string, string> = {
  running: "执行中", pending: "等待", waiting: "等待", queued: "排队", completed: "已完成", succeeded: "已完成",
  paused: "已暂停", stopped: "已停止", interrupted: "已中断，可恢复", failed: "失败", degraded: "降级",
  partial_failed: "部分失败", partial_failure: "部分失败", blocked: "受阻", skipped: "跳过", stopping: "正在停止",
  partial: "部分失败",
  pausing: "正在暂停", quota_exhausted: "配额耗尽", "quota-exhausted": "配额耗尽", complete: "交付完整", incomplete: "交付不完整",
  connecting: "连接事件流", connected: "事件流已连接", disconnected: "事件流断开，重连中",
};
const PASSIVE = new Set(["search", "company_lookup", "passive_subdomains", "osint", "passive_supply_chain"]);
const VERIFY = new Set(["dns_recursive", "tcp_scan", "service_probe", "web_visit", "tls_inspect", "screenshot"]);
const CREDENTIAL_FIELDS = ["FOFA_EMAIL", "FOFA_KEY", "QUAKE_TOKEN", "HUNTER_KEY", "ZOOEYE_KEY", "SHODAN_KEY", "CENSYS_ID", "CENSYS_SECRET"];
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const json = (value: any) => JSON.stringify(value, null, 2);
const text = (value: any) => value === null || value === undefined ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
const list = (value: string) => value.split(/[\n,，]/).map(item => item.trim()).filter(Boolean);
const isInScope = (asset: JsonObject) => ["in_scope", "in-scope", "in", "included"].includes(asset.scope_status) &&
  !asset.quarantine && !asset.quarantined && asset.review_status !== "excluded" && !["quarantined", "quarantine", "isolated"].includes(asset.verification_status);

function presetCapabilities(catalog: ModeCatalog, mode: string, visited = new Set<string>()): string[] {
  if (visited.has(mode)) return [];
  visited.add(mode);
  const preset = catalog.presets[mode] || {};
  const parent = preset.extends ? presetCapabilities(catalog, preset.extends, visited) : [];
  return [...new Set([...(preset.capabilities || parent), ...(preset.add_capabilities || [])])];
}

function presetSteps(catalog: ModeCatalog, mode: string): string[] {
  const preset = catalog.presets[mode] || {};
  const resolve = (name: string, seen = new Set<string>()): string[] => {
    if (seen.has(name)) return [];
    seen.add(name);
    const plan = catalog.plans?.[name] || {};
    return [...new Set([...(plan.steps || (plan.extends ? resolve(plan.extends, seen) : [])), ...(plan.add_steps || [])])] as string[];
  };
  return preset.default_plan ? resolve(preset.default_plan) : presetCapabilities(catalog, mode);
}

function newConfiguration(catalog: ModeCatalog): JsonObject {
  const mode = catalog.presets.passive_discovery ? "passive_discovery" : Object.keys(catalog.presets)[0];
  const scope = () => ({ include: [], exclude: [], subjects: [], brands: [], domain_match: "exact" });
  return {
    schema_version: 2, name: "", project_purpose: "investigation", mode_preset: mode, authorization: false,
    execution: { source: "replay", target_local: false, evidence_dir: "" },
    targets: { company: "", roots: [], ip_cidrs: [], brands: [] },
    scope_sets: { investigation: scope(), verification: scope(), extended: scope() },
    permissions: Object.fromEntries(Object.keys(catalog.capability_catalog).map(capability => [capability,
      { allow: false, scope_ref: PASSIVE.has(capability) ? "investigation" : VERIFY.has(capability) ? "verification" : "extended" }])),
    plan: { selection: "auto", selected_capabilities: presetSteps(catalog, mode), params: {} },
    budgets: { ...(catalog.defaults?.budgets || {}) },
    reports: { variants: ["professional", "user_custom"], formats: ["csv", "html", "md"], snapshot_policy: "immutable" },
  };
}

function Badge({ state }: { state: string }) {
  return <span className="wb-badge" data-state={state}>{state === "running" && <span className="wb-tool-dot" />}{STATE_LABELS[state] || state || "未开始"}</span>;
}

function Field({ label, children, wide = false }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return <label className={`wb-field${wide ? " wb-span3" : ""}`}><span className="wb-field-label">{label}</span>{children}</label>;
}

function ConfigurationEditor({ catalog, initial, onSave, busy, onCancel, existing }: {
  catalog: ModeCatalog; initial: JsonObject; onSave: (config: JsonObject) => Promise<void>;
  busy: boolean; onCancel: () => void; existing: boolean;
}) {
  const [config, setConfig] = useState<JsonObject>(() => clone(initial));
  const [advanced, setAdvanced] = useState(() => json(initial));
  const [parseError, setParseError] = useState("");
  const [paramsText, setParamsText] = useState<Record<string, string>>({});
  const [paramsError, setParamsError] = useState<Record<string, string>>({});
  const [rawText, setRawText] = useState<Record<string, string>>({});
  const capabilities = Object.keys(catalog.capability_catalog);
  const available = presetCapabilities(catalog, config.mode_preset);
  const selected: string[] = config.plan?.selection === "auto" ? presetSteps(catalog, config.mode_preset) : config.plan?.selected_capabilities || [];

  const mutate = (callback: (next: JsonObject) => void) => {
    const next = clone(config);
    callback(next);
    setConfig(next); setAdvanced(json(next)); setParseError("");
  };
  const patchTarget = (key: string, value: any) => mutate(next => {
    const oldSeeds = new Set([...(next.targets?.roots || []), ...(next.targets?.ip_cidrs || [])]);
    next.targets = { ...next.targets, [key]: value };
    if (key === "company") next.scope_sets.investigation.subjects = value.trim() ? [value.trim()] : [];
    if (key === "brands") next.scope_sets.investigation.brands = value;
    if (key === "roots" || key === "ip_cidrs") {
      const preserved = (next.scope_sets.investigation.include || []).filter((item: string) => !oldSeeds.has(item));
      next.scope_sets.investigation.include = [...new Set([...preserved, ...(next.targets.roots || []), ...(next.targets.ip_cidrs || [])])];
      setRawText(current => { const updated = { ...current }; delete updated.investigation; return updated; });
    }
  });
  const fixture = () => { setRawText({}); setParamsText({}); setParamsError({}); mutate(next => {
    next.name ||= "本地 ASM 验证";
    next.mode_preset = "full_asm";
    next.authorization = true;
    next.authorization_details = { authority: "fixture_owner", reference: "self_owned_local_fixture", environment: "local_lab",
      window: { start: null, end: null, policy: "owner_controlled_local_fixture" } };
    next.execution = { source: "live", target_local: true };
    next.targets = { company: "Fixture Example Organization", roots: ["localhost"], ip_cidrs: ["127.0.0.1/32", "::1/128"], brands: [] };
    for (const scope of Object.keys(next.scope_sets)) next.scope_sets[scope].include = ["localhost", "127.0.0.1/32", "::1/128"];
    const choices = ["tcp_scan", "udp_scan", "service_probe", "web_visit", "web_path_enum", "exposure_check", "screenshot"];
    for (const capability of capabilities) next.permissions[capability].allow = choices.includes(capability);
    next.plan = { selection: "custom", selected_capabilities: choices, params: {
      tcp_scan: { ports: "8765,8766,8768" }, udp_scan: { ports: "8767" },
      web_visit: { urls: ["http://127.0.0.1:8765"], timeout_seconds: 5 },
      web_path_enum: { max_requests_per_host: 20 }, screenshot: { full_page: true },
    } };
    next.budgets = { ...next.budgets, max_rounds: 1, max_hosts: 3, max_duration_seconds: 600 };
  }); };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (parseError || Object.values(paramsError).some(Boolean)) return;
    await onSave(config);
  };

  return <form className="wb-panel wb-editor" onSubmit={save}>
    <div className="wb-section-head"><h2>{existing ? "编辑项目配置" : "新建调查项目"}</h2><div className="wb-actions">
      <button type="button" onClick={fixture} disabled={busy}>载入本地 fixture 配置</button>
      <button type="button" onClick={onCancel} disabled={busy}>取消</button>
    </div></div>
    <div className="wb-form-grid">
      <Field label="项目名称"><input required value={config.name || ""} onChange={event => mutate(next => { next.name = event.target.value; })} /></Field>
      <Field label="权限预设"><select value={config.mode_preset} onChange={event => mutate(next => {
        next.mode_preset = event.target.value;
        if (next.plan.selection === "auto") next.plan.selected_capabilities = presetSteps(catalog, next.mode_preset);
      })}>{Object.entries(catalog.presets).map(([key, preset]) => <option key={key} value={key}>{preset.label || key}</option>)}</select></Field>
      <Field label="执行来源"><select value={config.execution?.source || "replay"} onChange={event => mutate(next => {
        next.execution = { ...next.execution, source: event.target.value };
      })}><option value="replay">回放 · 仅已有离线证据</option><option value="live">实跑 · 依照范围与逐功能权限</option></select></Field>
      <Field label="主体名称"><input value={config.targets?.company || ""} onChange={event => patchTarget("company", event.target.value)} placeholder="公司或组织名称" /></Field>
      <Field label="域名种子（逗号或换行）"><textarea value={rawText.roots ?? (config.targets?.roots || []).join("\n")} onChange={event => {
        setRawText(current => ({ ...current, roots: event.target.value })); patchTarget("roots", list(event.target.value));
      }} placeholder="填写获准调查的域名" /></Field>
      <Field label="IP / CIDR 种子"><textarea value={rawText.ip_cidrs ?? (config.targets?.ip_cidrs || []).join("\n")} onChange={event => {
        setRawText(current => ({ ...current, ip_cidrs: event.target.value })); patchTarget("ip_cidrs", list(event.target.value));
      }} placeholder="127.0.0.1/32" /></Field>
      <Field label="品牌关键词"><input value={rawText.brands ?? (config.targets?.brands || []).join(", ")} onChange={event => {
        setRawText(current => ({ ...current, brands: event.target.value })); patchTarget("brands", list(event.target.value));
      }} /></Field>
      <Field label="自动流程 / 自定义选择"><select value={config.plan?.selection || "auto"} onChange={event => mutate(next => {
        next.plan = { ...next.plan, selection: event.target.value, selected_capabilities: presetSteps(catalog, config.mode_preset) };
      })}><option value="auto">默认自动流程</option><option value="custom">自定义功能与工具参数</option></select></Field>
      <Field label="预算 · 最大迭代轮次"><input type="number" min="1" value={config.budgets?.max_rounds || 1} onChange={event => mutate(next => {
        next.budgets = { ...next.budgets, max_rounds: Number(event.target.value) };
      })} /></Field>
      {config.execution?.source === "replay" && <Field wide label="已有离线证据目录"><input value={config.execution?.evidence_dir || ""} onChange={event => mutate(next => {
        next.execution = { ...next.execution, evidence_dir: event.target.value };
      })} placeholder="本机已有交付或 evidence 目录；后端只读取留档" /></Field>}
    </div>
    <p className="wb-muted" style={{ marginTop: 16 }}>{catalog.presets[config.mode_preset]?.description}</p>
    <div className="wb-actions">
      <label className="wb-check"><input type="checkbox" checked={config.authorization === true} onChange={event => mutate(next => { next.authorization = event.target.checked; })} />当前项目已取得主动测试授权</label>
      <label className="wb-check"><input type="checkbox" checked={config.execution?.target_local === true} onChange={event => mutate(next => {
        next.execution = { ...next.execution, target_local: event.target.checked };
      })} />自有本地 / 内网 fixture</label>
    </div>
    <div className="wb-form-grid" style={{ marginTop: 16 }}>
      {(["investigation", "verification", "extended"] as const).map((scope, index) => <Field key={scope} label={["调查范围（被动与反馈）", "主动核实范围", "深入主动范围"][index]}>
        <textarea value={rawText[scope] ?? (config.scope_sets?.[scope]?.include || []).join("\n")} onChange={event => {
          setRawText(current => ({ ...current, [scope]: event.target.value })); mutate(next => {
            next.scope_sets ||= {}; next.scope_sets[scope] = { ...next.scope_sets[scope], include: list(event.target.value) };
          });
        }} placeholder="精确域名 / IP / CIDR，每行一项" />
      </Field>)}
    </div>
    <p className="wb-muted" style={{ marginTop: 10 }}>调查范围与主动权限分别保存。预设提供计划；每个功能还需明确允许且落在对应范围。互联网主动授权的批准引用与时间窗口在高级配置中填写。</p>
    <details className="wb-detail"><summary>限制可运行的工具（可选）</summary><p className="wb-muted">不勾选工具限制时使用每项功能的默认工具。勾选后仅使用这些工具，相应未匹配功能不会执行。</p><div className="wb-actions">
      {[...new Set(capabilities.flatMap(capability => catalog.capability_catalog[capability].adapter_candidates || []))].map(tool => <label key={tool} className="wb-check"><input type="checkbox" checked={(config.plan?.selected_tools || []).includes(tool)} onChange={event => mutate(next => {
        const chosen = new Set<string>(next.plan.selected_tools || []);
        if (event.target.checked) chosen.add(tool); else chosen.delete(tool);
        next.plan.selected_tools = [...chosen];
        for (const [capability, info] of Object.entries(catalog.capability_catalog)) {
          const candidates = (info as { adapter_candidates?: string[] }).adapter_candidates || [];
          const selected = candidates.filter(tool => chosen.has(tool));
          if (selected.length > 1 || (selected.length && next.tools?.[capability] && !selected.includes(next.tools[capability]))) {
            if (next.tools) delete next.tools[capability];
            if (next.plan.params?.[capability]) delete next.plan.params[capability].engine;
          }
        }
      })} />{tool}</label>)}
    </div></details>
    <div className="wb-permissions">
      {capabilities.map(capability => {
        const permission = config.permissions?.[capability] || {};
        const info = catalog.capability_catalog[capability];
        const params = config.plan?.params?.[capability] || {};
        const parameterError = paramsError[capability];
        return <div className="wb-capability" key={capability}>
          <div><label><input type="checkbox" checked={selected.includes(capability)} disabled={config.plan?.selection !== "custom" || !available.includes(capability)} onChange={event => mutate(next => {
            const set = new Set<string>(next.plan.selected_capabilities || []);
            if (event.target.checked) set.add(capability); else set.delete(capability);
            next.plan.selected_capabilities = [...set];
          })} /><strong>{LABELS[capability] || capability}</strong></label>
          <small>{info.active_target_traffic ? "主动能力" : "第三方公开情报"} · {capability}</small><small>接入状态：{info.adapter_status || "后端未提供"}</small></div>
          <div><label><input type="checkbox" checked={permission.allow === true} onChange={event => mutate(next => {
            next.permissions ||= {}; next.permissions[capability] = { ...permission, allow: event.target.checked,
              scope_ref: permission.scope_ref || (PASSIVE.has(capability) ? "investigation" : VERIFY.has(capability) ? "verification" : "extended") };
          })} />允许执行</label><small>{selected.includes(capability) ? "已列入计划" : "未选择，不执行"}</small></div>
          <div><label className="wb-field">功能范围<select value={permission.scope_ref || (PASSIVE.has(capability) ? "investigation" : VERIFY.has(capability) ? "verification" : "extended")} onChange={event => mutate(next => {
            next.permissions ||= {}; next.permissions[capability] = { ...permission, scope_ref: event.target.value };
          })}>{Object.keys(config.scope_sets || {}).map(scope => <option key={scope} value={scope}>{scope}</option>)}</select></label>
          <label className="wb-field" style={{ marginTop: 8 }}>工具<select value={config.tools?.[capability] || ""} onChange={event => mutate(next => {
            next.tools ||= {};
            if (event.target.value) next.tools[capability] = event.target.value; else delete next.tools[capability];
          })}><option value="">后端默认选择</option>{(info.adapter_candidates || []).map((tool: string) => <option key={tool} value={tool}>{tool}</option>)}</select></label></div>
          <div><label className="wb-field">工具参数 JSON<textarea aria-label={`${LABELS[capability] || capability}参数`} value={paramsText[capability] ?? json(params)} onChange={event => {
            const value = event.target.value; setParamsText(current => ({ ...current, [capability]: value }));
            try {
              const parsed = JSON.parse(value || "{}");
              if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("参数须为 JSON 对象");
              mutate(next => { next.plan.params ||= {}; next.plan.params[capability] = parsed; });
              setParamsError(current => ({ ...current, [capability]: "" }));
            } catch { setParamsError(current => ({ ...current, [capability]: "JSON 参数不可解析" })); }
          }} /></label>{parameterError && <small role="alert" style={{ color: "#982820" }}>{parameterError}</small>}</div>
        </div>;
      })}
    </div>
    <details className="wb-detail"><summary>有效项目配置 · 高级 JSON 编辑（后端保存为 YAML）</summary>
      <p className="wb-muted">可设置工具选择、排除范围、精确匹配、批准引用与时间窗口、解析器及其他参数。项目配置不得包含 API 密钥。</p>
      <textarea className="wb-json" value={advanced} aria-label="有效项目配置" onChange={event => {
        setAdvanced(event.target.value);
        try {
          const parsed = JSON.parse(event.target.value);
          if (!parsed || Array.isArray(parsed) || typeof parsed !== "object" ||
              !["targets", "scope_sets", "permissions", "plan"].every(key => parsed[key] && typeof parsed[key] === "object" && !Array.isArray(parsed[key]))) throw new Error();
          setConfig(parsed); setRawText({}); setParamsText({}); setParamsError({}); setParseError("");
        } catch { setParseError("配置 JSON 不可解析，修复后才能保存。"); }
      }} />
      {parseError && <p role="alert" style={{ color: "#982820" }}>{parseError}</p>}
    </details>
    <div className="wb-actions" style={{ marginTop: 16 }}><button type="submit" className="wb-primary" disabled={busy || !!parseError || Object.values(paramsError).some(Boolean)}>{busy ? "正在保存…" : existing ? "保存配置及权限修订" : "创建项目"}</button></div>
  </form>;
}

function SettingsPanel({ onClose, onError }: { onClose: () => void; onError: (error: unknown) => void }) {
  const [summary, setSummary] = useState<JsonObject | null>(null);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { workbenchApi.settings().then(setSummary).catch(onError); }, [onError]);
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setNotice("");
    try {
      const supplied = Object.fromEntries(Object.entries(credentials).filter(([, value]) => value));
      setSummary(await workbenchApi.saveSettings(supplied));
      setCredentials({}); setNotice("凭据已保存到后端秘密配置；这里只显示配置摘要。");
    } catch (error) { onError(error); } finally { setSaving(false); }
  };
  return <form className="wb-panel wb-settings" onSubmit={save}><div className="wb-section-head"><h2>后端 API 配置</h2><button type="button" onClick={onClose}>关闭</button></div>
    <p className="wb-muted">输入仅用于提交给本机后端。空值保留现有配置；前端不持久保存凭据，成功后清空输入。</p>
    {summary && <div className="wb-history">{Object.entries(summary.providers || {}).map(([provider, value]) => <span key={provider} className="wb-badge">{provider}：{(value as JsonObject).configured ? "已配置" : "未配置"}</span>)}</div>}
    {notice && <div className="wb-alert wb-notice" role="status">{notice}</div>}
    <div className="wb-form-grid">{CREDENTIAL_FIELDS.map(field => <Field key={field} label={field}><input type="password" autoComplete="new-password" value={credentials[field] || ""} onChange={event => setCredentials(current => ({ ...current, [field]: event.target.value }))} placeholder="空值保留后端现有配置" /></Field>)}</div>
    <div className="wb-actions" style={{ marginTop: 16 }}><button className="wb-primary" disabled={saving}>{saving ? "正在保存…" : "保存到后端"}</button><span className="wb-muted">FOFA 限速 ≥{summary?.policy?.fofa_min_interval || 15}s，账户用量跨项目保留。</span></div>
  </form>;
}

export function Workbench({ onDemo, onReplay }: { onDemo?: () => void; onReplay?: () => void }) {
  const [catalog, setCatalog] = useState<ModeCatalog | null>(null);
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [files, setFiles] = useState<Artifact[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [toolCalls, setToolCalls] = useState<JsonObject[]>([]);
  const [connection, setConnection] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<JsonObject | null>(null);
  const [creating, setCreating] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [pauseScroll, setPauseScroll] = useState(false);
  const [fileFilter, setFileFilter] = useState("");
  const [preview, setPreview] = useState<{ path: string; content: string } | null>(null);
  const [planned, setPlanned] = useState<JsonObject | null>(null);
  const [bundle, setBundle] = useState<JsonObject | null>(null);
  const [reviewAsset, setReviewAsset] = useState<JsonObject | null>(null);
  const [reviewStatus, setReviewStatus] = useState("reviewed");
  const [reviewNote, setReviewNote] = useState("");
  const [reviewEvidence, setReviewEvidence] = useState<string[]>([]);
  const [corroborated, setCorroborated] = useState(false);
  const [scopeValue, setScopeValue] = useState("");
  const [historyId, setHistoryId] = useState("");
  const logEnd = useRef<HTMLDivElement>(null);
  const reloadTimer = useRef<ReturnType<typeof setTimeout>>();
  const selectedProjectId = useRef<string | null>(null);
  const selectedRunId = useRef("");
  const refreshVersion = useRef(0);
  const describeError = useCallback((failure: unknown) => setError(failure instanceof Error ? failure.message : String(failure)), []);

  const refreshRun = useCallback(async (id: string) => {
    const version = ++refreshVersion.current;
    const current = selectedRunId.current ? await workbenchApi.runState(selectedRunId.current) : await workbenchApi.run(id);
    if (selectedProjectId.current !== id || version !== refreshVersion.current) return;
    setRun(current);
    if (current?.run_id) {
      const artifactList = await workbenchApi.artifacts(current.run_id);
      const hasLog = artifactList.some(file => file.path.replace(/\\/g, "/") === "logs/tool-calls.jsonl");
      const calls = hasLog ? await workbenchApi.toolCalls(current.run_id) : [];
      if (selectedProjectId.current !== id || version !== refreshVersion.current) return;
      setFiles(artifactList || []); setToolCalls(calls);
    } else { setFiles([]); setToolCalls([]); }
  }, []);

  const openProject = useCallback(async (item: ProjectRecord) => {
    setPlanned(null);
    setBundle(null);
    setReviewAsset(null);
    selectedProjectId.current = item.project_id; selectedRunId.current = ""; setHistoryId("");
    setProject(item); setRun(null); setEvents([]); setToolCalls([]); setFiles([]); setPreview(null); setEditing(null); setCreating(false); setError("");
    try { localStorage.setItem("asm-workbench:selected-project", item.project_id); } catch { /* Non-secret UI state only. */ }
    try { await refreshRun(item.project_id); }
    catch (failure) { if (!(failure instanceof ApiError && failure.status === 404)) describeError(failure); }
  }, [refreshRun, describeError]);

  const loadProjects = useCallback(async (restore = false) => {
    setLoading(true); setError("");
    try {
      const [modes, availableProjects] = await Promise.all([workbenchApi.modes(), workbenchApi.projects()]);
      setCatalog(modes); setProjects(availableProjects || []);
      if (restore) {
        let stored = "";
        try { stored = localStorage.getItem("asm-workbench:selected-project") || ""; } catch { /* Storage optional. */ }
        const existing = availableProjects.find(item => item.project_id === stored);
        if (existing && (existing.purpose || "investigation") === "investigation") await openProject(existing);
      }
    } catch (failure) { describeError(failure); } finally { setLoading(false); }
  }, [openProject, describeError]);

  useEffect(() => { void loadProjects(true); }, [loadProjects]);
  useEffect(() => {
    if (!project) return;
    const interval = setInterval(() => void refreshRun(project.project_id).catch(describeError), 4000);
    return () => clearInterval(interval);
  }, [project?.project_id, refreshRun, describeError]);
  useEffect(() => {
    if (!run?.run_id || !project) return;
    setEvents([]);
    const currentProject = project.project_id;
    const close = subscribeRun(run.run_id, event => {
      setEvents(current => current.some(item => item.id === event.id) ? current : [...current, event].slice(-500));
      if (reloadTimer.current) clearTimeout(reloadTimer.current);
      reloadTimer.current = setTimeout(() => void refreshRun(currentProject).catch(describeError), 180);
    }, setConnection);
    return () => { close(); if (reloadTimer.current) clearTimeout(reloadTimer.current); };
  }, [run?.run_id, project?.project_id, refreshRun, describeError]);
  useEffect(() => { if (!pauseScroll) logEnd.current?.scrollIntoView({ block: "nearest" }); }, [toolCalls.length, pauseScroll]);

  const action = async (task: () => Promise<void>) => {
    setBusy(true); setError(""); setNotice("");
    try { await task(); } catch (failure) { describeError(failure); } finally { setBusy(false); }
  };
  const saveConfiguration = async (config: JsonObject) => action(async () => {
    setPlanned(null);
    if (creating) {
      const result = await workbenchApi.create(config);
      const refreshed = await workbenchApi.projects(); setProjects(refreshed);
      const item = refreshed.find(candidate => candidate.project_id === result.project_id) || result;
      await openProject(item); setNotice("项目已创建；启动前后端会再次校验范围、权限、工具与参数。");
    } else if (project) {
      await workbenchApi.saveConfig(project.project_id, config);
      const saved = await workbenchApi.config(project.project_id);
      setProject(current => current ? { ...current, config: saved.config, path: saved.path, revision: saved.revision } : current);
      setEditing(null); setNotice("配置与权限修订已保存。后续动作依照当前有效权限执行。");
      await refreshRun(project.project_id);
    }
  });
  const start = () => project && action(async () => {
    const started = await workbenchApi.start(project.project_id);
    selectedRunId.current = ""; setHistoryId(""); setRun(started); setEvents([]); setPreview(null);
    const latestProjects = await workbenchApi.projects(); setProjects(latestProjects);
    const latestProject = latestProjects.find(item => item.project_id === project.project_id);
    if (latestProject) setProject(latestProject);
    await refreshRun(project.project_id);
  });
  const control = (operation: "pause" | "resume" | "stop" | "export") => run && project && action(async () => {
    await workbenchApi.control(run.run_id, operation); await refreshRun(project.project_id);
    if (operation === "export") setNotice("已创建新的导出快照；旧快照保持留档。请检查 manifest 的交付状态。");
  });
  const edit = () => project && action(async () => {
    const saved = await workbenchApi.config(project.project_id);
    setCreating(false); setEditing(saved.config);
  });
  const addScope = (value: string) => project && action(async () => {
    if (!value.trim()) return;
    await workbenchApi.scope(project.project_id, value.trim());
    setPlanned(null);
    const saved = await workbenchApi.config(project.project_id);
    setProject(current => current ? { ...current, config: saved.config, revision: saved.revision } : current);
    setScopeValue(""); setNotice("已加入调查范围。主动核实范围与逐功能权限仍需独立配置；继续运行处理未完成步骤。");
    await refreshRun(project.project_id);
  });
  const saveReview = () => run && project && reviewAsset && action(async () => {
    await workbenchApi.review(run.run_id, { asset_id: reviewAsset.asset_id, status: reviewStatus, note: reviewNote,
      evidence_ids: reviewEvidence, corroborated: reviewStatus === "reviewed" && corroborated });
    setReviewAsset(null);
    setNotice("复核记录已保存。归属、核实、置信度与授权范围独立保留；创建新快照后报告包含此次复核。");
    await refreshRun(project.project_id);
  });

  const assets = run?.assets || [];
  const scoped = assets.filter(isInScope);
  const excluded = assets.filter(asset => !isInScope(asset));
  const extraLeads = run?.leads || run?.out_of_scope_leads || [];
  const allLeads = [...excluded, ...extraLeads.filter((lead: JsonObject) => !excluded.some(asset => asset.asset_id && asset.asset_id === lead.asset_id))];
  const steps = run?.steps || [];
  const finishedSteps = steps.filter(step => ["completed", "succeeded", "skipped"].includes(step.status)).length;
  const reportFiles = files.filter(file => /exports\/.+\/(professional|user_custom)\/[^/]+\.(csv|html|md)$/.test(file.path.replace(/\\/g, "/")));
  const visibleFiles = files.filter(file => file.path.toLowerCase().includes(fileFilter.toLowerCase()));
  const active = run && ["running", "queued", "pausing", "stopping"].includes(run.status);
  const resumable = run && ["paused", "interrupted", "stopped", "partial", "partial_failed", "partial_failure", "failed"].includes(run.status);
  const currentConfig = project?.config || run?.config || {};

  const assetTable = (rows: JsonObject[], leads = false) => rows.length ? <div className="wb-table-wrap"><table><thead><tr>
    <th>资产 / 线索</th><th>IP / 协议 / 端口</th><th>实际标题 / 服务</th><th>归属与核实</th><th>证据 / 范围</th><th>人工复核</th>{leads && <th>调查范围</th>}
  </tr></thead><tbody>{rows.map((asset, index) => <tr key={asset.asset_id || `${asset.domain || asset.ip || asset.name}-${index}`}>
    <td><strong>{asset.domain || asset.name || asset.host || asset.ip || asset.asset_id || "未标注"}</strong><div className="wb-muted">{asset.url}</div><small>{asset.asset_id}</small></td>
    <td>{text(asset.ip)}<br />{asset.protocol || asset.proto || ""}{asset.port !== undefined && asset.port !== null ? ` / ${asset.port}` : ""}</td>
    <td>{asset.title || asset.service || "未观测"}<br /><small>{text(asset.technology || asset.version)}</small></td>
    <td>{asset.attribution_status === "verified" || asset.attribution_status === "confirmed" ? asset.organization || "待确认" : "待确认"}<br /><small>{asset.verification_status || "未标注核实状态"}</small></td>
    <td>{text(asset.evidence_ids)}<br /><small>{asset.scope_status || "范围待确认"}{asset.quarantine ? " · 隔离" : ""}</small></td>
    <td>{asset.review_status === "reviewed" ? "已复核" : asset.review_status === "excluded" ? "已排除" : "待复核"}<br /><small>{asset.corroboration_status === "corroborated" ? "人工确认独立来源佐证" : "尚未确认独立佐证"}</small><br /><button disabled={busy} onClick={() => {
      setReviewAsset(asset); setReviewStatus(asset.review_status || "reviewed"); setReviewNote(asset.manual_review?.note || "");
      setReviewEvidence(asset.review_evidence || []); setCorroborated(asset.corroboration_status === "corroborated");
    }}>复核证据</button></td>
    {leads && <td><button disabled={busy} onClick={() => addScope(asset.domain || asset.host || asset.ip || asset.name || "")}>手动加入调查范围</button></td>}
  </tr>)}</tbody></table></div> : <p className="wb-muted">{leads ? "暂无范围外或隔离线索。" : "尚无范围内观测。执行结果会从后端增量出现；空表不表示没有暴露或风险。"}</p>;

  return <div className="wb">
    <header className="wb-header"><div><h1>ASM Workbench</h1><p>调查 · 核实 · 证据 · 双版本交付</p></div><div className="wb-header-actions">
      {project && <button onClick={() => {
        selectedProjectId.current = null; setProject(null); setRun(null); setEditing(null); setCreating(false);
        try { localStorage.removeItem("asm-workbench:selected-project"); } catch { /* Optional storage. */ }
        void loadProjects();
      }}>项目列表</button>}
      <button onClick={() => setShowSettings(current => !current)}>API 配置</button>
      {onDemo && <button onClick={onDemo}>虚构演示</button>}{onReplay && <button onClick={onReplay}>历史证据浏览</button>}
    </div></header>
    <main className="wb-shell">
      {error && <div className="wb-alert" role="alert"><strong>操作未完成：</strong>{error}<div className="wb-actions" style={{ marginTop: 8 }}><button onClick={() => project ? refreshRun(project.project_id).catch(describeError) : loadProjects()}>重试读取后端</button><button onClick={() => setError("")}>关闭提示</button></div></div>}
      {notice && <div className="wb-alert wb-notice" role="status">{notice}</div>}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} onError={describeError} />}
      {!project && <><ProjectCenter projects={projects} loading={loading} busy={busy} canCreate={!!catalog} onOpen={openProject} onRefresh={() => void loadProjects()} onHistory={onReplay} onDemo={onDemo} onCreate={() => {
        if (catalog) { setCreating(true); setEditing(newConfiguration(catalog)); setError(""); }
      }} />
      {editing && catalog && <ConfigurationEditor catalog={catalog} initial={editing} onSave={saveConfiguration} busy={busy} onCancel={() => { setEditing(null); setCreating(false); }} existing={false} />}</>}
      {project && <>
        <div className="wb-run-summary"><div><h2>{currentConfig.name || project.name || project.project_id}</h2><p className="wb-muted">{catalog?.presets[currentConfig.mode_preset]?.label || currentConfig.mode_preset} · {currentConfig.execution?.source === "replay" ? "已有证据离线回放" : "真实执行"} · 配置修订 {project.revision ?? "未标注"}</p><p className="wb-path">{project.path}</p></div>
        <div className="wb-actions"><button onClick={edit} disabled={busy}>配置 / 工具 / 权限</button><button onClick={() => action(async () => setPlanned(await workbenchApi.plan(project.project_id)))} disabled={busy || !!editing}>预览执行计划</button><button className="wb-primary" onClick={start} disabled={busy || !!active || !!editing}>新运行</button></div></div>
        {planned && <section className="wb-panel" data-testid="plan-preview" style={{ marginBottom: 17 }}><div className="wb-section-head"><h3>启动前执行计划</h3><button onClick={() => setPlanned(null)}>关闭计划预览</button></div><p className="wb-muted">{planned.source === "replay" ? "已有证据离线回放" : "真实执行"} · 配置哈希 {planned.config_hash} · 模式版本 {planned.mode_version}</p><p className="wb-muted">权限、范围和依赖会在每个动作执行前再次检查。预览不启动工具，也不表示检测已完成。</p><div className="wb-table-wrap"><table><thead><tr><th>功能 / 工具</th><th>对象</th><th>权限与依赖</th><th>有效参数</th></tr></thead><tbody>{(planned.steps || []).map((step: JsonObject, index: number) => <tr key={`${step.capability}-${step.tool}-${step.target}-${index}`}><td>{LABELS[step.capability] || step.capability}<br /><small>{step.tool}</small></td><td>{step.target || "缺少输入"}</td><td>{step.permitted ? "范围与权限允许" : "当前不可执行"}<br /><small>{step.reason}</small><br /><small>{step.dependencies?.reason || "依赖将在执行时校验"}</small></td><td><details><summary>查看参数</summary><pre className="wb-preview">{json(step.params)}</pre></details></td></tr>)}</tbody></table></div><details><summary>预算与配置版本</summary><pre className="wb-preview">{json({ budgets: planned.budgets, permission_version: planned.permission_version })}</pre></details></section>}
        {editing && catalog && <ConfigurationEditor key={project.project_id} catalog={catalog} initial={editing} onSave={saveConfiguration} busy={busy} onCancel={() => setEditing(null)} existing />}
        {!!project.runs?.length && <label className="wb-field" style={{ maxWidth: 650, marginBottom: 17 }}>运行记录<select value={historyId} onChange={event => {
          selectedRunId.current = event.target.value; setHistoryId(event.target.value); setPreview(null);
          void refreshRun(project.project_id).catch(describeError);
        }}><option value="">最新运行（自动刷新）</option>{project.runs.map(item => <option key={item.id || item.run_id} value={item.id || item.run_id}>{item.id || item.run_id} · {STATE_LABELS[item.status] || item.status} · {item.started || item.started_at || ""}</option>)}</select></label>}
        {!run && !editing && <div className="wb-empty"><h3>项目配置已保存</h3><p>点击“新运行”生成后端执行计划并开始获准步骤。配置或依赖缺失会显示实际原因。</p></div>}
        {run && <>
          <div className="wb-panel wb-run-summary"><div><Badge state={run.status} /> <span className="wb-path">{run.run_id}</span><p className="wb-path">{run.directory}</p><small>检查点、已完成步骤与账户用量由后端持久保存。</small></div><div className="wb-actions">
            <Badge state={connection} /><button onClick={() => control("pause")} disabled={busy || !active}>暂停任务</button>
            <button onClick={() => control("resume")} disabled={busy || !resumable}>继续 / 中断恢复</button>
            <button className="wb-danger" onClick={() => control("stop")} disabled={busy || !active}>停止并保留证据</button>
            <button onClick={() => control("export")} disabled={busy}>创建交付快照</button>
          </div></div>
          <div className="wb-stats"><div className="wb-stat"><strong>{scoped.length}</strong><small>范围内资产 · 与双报告主表同口径</small></div><div className="wb-stat"><strong>{allLeads.length}</strong><small>范围外 / 隔离 / 未确认范围</small></div><div className="wb-stat"><strong>{finishedSteps} / {steps.length}</strong><small>完成或有理由跳过的执行步骤</small></div><div className="wb-stat"><strong>{toolCalls.length}</strong><small>磁盘工具调用日志 · 同源读取</small></div></div>
          {run.snapshot && <div className={`wb-alert ${run.snapshot.status === "incomplete" ? "" : "wb-notice"}`}><strong>{run.snapshot.status === "incomplete" ? "当前交付不完整" : "当前交付快照"}</strong> · {run.snapshot.snapshot_id || ""} · 数据截止 {run.snapshot.data_cutoff || "未标注"}<br />{run.snapshot.status === "incomplete" ? text(run.snapshot.errors) : "专业完整版与用户定制版来自同一事实快照。"}</div>}
          {run.snapshot && <div className="wb-actions" style={{ marginBottom: 17 }}><button disabled={busy} onClick={() => action(async () => setBundle(await workbenchApi.bundle(run.run_id, run.snapshot!.snapshot_id)))}>生成完整证据包</button>{bundle?.run_id === run.run_id && <a href={workbenchApi.fileUrl(run.run_id, bundle.path)} download>下载快照 {bundle.snapshot_id} · {bundle.bytes} B · {bundle.status === "complete" ? "交付完整" : "交付不完整"}</a>}</div>}
          {reportFiles.length > 0 && <details className="wb-panel" open style={{ marginBottom: 17 }}><summary><strong>双版本报告 · 各 CSV / HTML / Markdown</strong></summary><div className="wb-report-links" style={{ marginTop: 12 }}>{reportFiles.map(file => <a key={file.path} href={workbenchApi.fileUrl(run.run_id, file.path)} target="_blank" rel="noreferrer">{file.path}</a>)}</div><small>文件树保留全部历史快照。运行表可能继续变化，导出文件以数据截止时间为准。</small></details>}
          {run.delivery_error && <div className="wb-alert" role="alert"><strong>最近一次导出失败，交付不完整。</strong> {text(run.delivery_error.reason)} · 已有快照仍保留；可重新创建交付快照。</div>}
          {reviewAsset && <section className="wb-panel" data-testid="asset-review" style={{ marginBottom: 17 }}><h3>复核资产证据</h3><p className="wb-path">{reviewAsset.asset_id} · {reviewAsset.domain || reviewAsset.ip || reviewAsset.name}</p><p className="wb-muted">复核状态与独立佐证分别记录。佐证需明确选中两家独立来源的匹配证据；归属、置信度、在线核实和主动授权仍按各自依据判断。</p><div className="wb-form-grid"><Field label="人工复核状态"><select value={reviewStatus} onChange={event => setReviewStatus(event.target.value)}><option value="pending">待复核</option><option value="reviewed">已复核</option><option value="excluded">人工排除</option></select></Field><Field label="复核依据" wide><textarea aria-label="复核依据" value={reviewNote} maxLength={2000} onChange={event => setReviewNote(event.target.value)} placeholder="记录证据依据，不填写凭据" /></Field></div><p>支持此次判断的已有证据：</p><div className="wb-actions">{(reviewAsset.evidence_ids || []).map((id: string) => <label key={id}><input type="checkbox" checked={reviewEvidence.includes(id)} onChange={event => setReviewEvidence(current => event.target.checked ? [...current, id] : current.filter(item => item !== id))} /> {id}</label>)}</div><label style={{ display: "block", margin: "15px 0" }}><input type="checkbox" disabled={reviewStatus !== "reviewed"} checked={corroborated} onChange={event => setCorroborated(event.target.checked)} /> 我已核对独立来源的匹配证据，记录为已佐证</label><div className="wb-actions"><button disabled={busy || (reviewStatus !== "pending" && !reviewNote.trim())} onClick={saveReview}>保存复核记录</button><button onClick={() => setReviewAsset(null)}>取消复核</button></div></section>}
          {run.snapshot?.comparison && <details className="wb-panel" style={{ marginBottom: 17 }}><summary><strong>快照比较 · {run.snapshot.comparison.status === "comparable" ? "有匹配的历史配置" : "暂无可比历史快照"}</strong></summary><p className="wb-muted">未再次观测不表示资产已移除或风险已修复。比较基于相同计划、权限和范围。</p><pre className="wb-preview">{json(run.snapshot.comparison)}</pre></details>}
          <div className="wb-four">
            <section className="wb-panel"><div className="wb-section-head"><h3>执行计划与工具状态</h3><small>真实事件驱动</small></div><div className="wb-tools">{steps.map((step, index) => <article className="wb-tool" data-state={step.status} key={step.step_id || `${step.capability}-${index}`}><div className="wb-tool-head"><strong>{LABELS[step.capability || step.feature] || step.capability || step.feature || step.tool}</strong><Badge state={step.status} /></div><p>工具：{step.tool || "内部处理"}</p>{step.reason && <p>{step.reason}</p>}<details><summary>有效参数 / 输出</summary><pre>{json({ params: step.params || {}, outputs: step.outputs || [], attempt_id: step.attempt_id || null })}</pre></details></article>)}</div>{!steps.length && <p className="wb-muted">后端尚未返回执行计划。</p>}</section>
            <section className="wb-panel"><div className="wb-section-head"><h3>证据与交付文件</h3><small>{files.length} 文件</small></div><input aria-label="过滤文件树" placeholder="搜索文件路径" value={fileFilter} onChange={event => setFileFilter(event.target.value)} /><div className="wb-file-list" style={{ marginTop: 10 }}>{visibleFiles.map(file => <div className="wb-file" key={file.path}><a href={workbenchApi.fileUrl(run.run_id, file.path)} target="_blank" rel="noreferrer">{file.path}</a><small>{file.bytes} B</small><button onClick={() => action(async () => {
              if (/\.(png|jpe?g|webp|gif|pdf|zip|sqlite|db)$/i.test(file.path)) { setNotice("该文件为图像或二进制内容；点击路径可打开或下载。预览仅显示文本证据。"); return; }
              setPreview({ path: file.path, content: await workbenchApi.preview(run.run_id, file.path) });
            })}>预览</button></div>)}</div>{preview && <details open className="wb-detail"><summary>{preview.path}</summary><pre className="wb-preview">{preview.content}</pre></details>}</section>
            <section className="wb-panel"><div className="wb-section-head"><h3>实时资产与观测</h3><small>范围内 {scoped.length} 项</small></div>{assetTable(scoped)}</section>
            <section className="wb-panel"><div className="wb-section-head"><h3>工具调用日志</h3><button onClick={() => setPauseScroll(value => !value)}>{pauseScroll ? "恢复自动滚动" : "暂停日志滚动"}</button></div><p className="wb-muted">同源文件：logs/tool-calls.jsonl · {toolCalls.length} 条；滚动控制不改变任务执行。</p><div className="wb-logs">{toolCalls.map((call, index) => <article className="wb-event" key={call.call_id || call.attempt_id || index}><div className="wb-event-top"><strong>{call.tool || call.capability || `调用 ${index + 1}`}</strong><span>{call.ts || call.started_at || ""} · {call.status || "未标注"}</span></div><pre>{json(call)}</pre></article>)}{!toolCalls.length && <p className="wb-muted">暂无已落盘工具调用。</p>}<div ref={logEnd} /></div><details className="wb-detail"><summary>实时控制事件（最近 {events.length} 条）</summary><div className="wb-logs">{events.map(event => <div className="wb-event" key={event.id}><div className="wb-event-top"><strong>#{event.id} · {event.kind}</strong><span>{event.ts}</span></div><pre>{json(event.data)}</pre></div>)}</div></details></section>
          </div>
          <section className="wb-panel wb-followup"><div className="wb-section-head"><h3>范围外与隔离线索</h3><small>手动加入后才继续调查</small></div>{assetTable(allLeads, true)}<div className="wb-actions" style={{ marginTop: 15 }}><input style={{ maxWidth: 390 }} aria-label="新增调查范围" placeholder="精确域名 / IP / CIDR" value={scopeValue} onChange={event => setScopeValue(event.target.value)} /><button onClick={() => addScope(scopeValue)} disabled={busy || !scopeValue.trim()}>加入调查范围</button></div><p className="wb-muted" style={{ marginTop: 12 }}>加入调查范围后不会自动获得主动测试权限。主动动作仍逐功能核对核实/深入范围与当前权限修订。</p></section>
        </>}
      </>}
    </main>
  </div>;
}

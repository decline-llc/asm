// ============================================================
// 数据服务层：所有读写经由此处，组件不直接绑定演示数组。
// 未来接入后端时替换本文件实现即可。
// 能力分级：backend（后端已支持）/ pending（待接入）/ demo（仅演示）
// ============================================================

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  assets as seedAssets,
  companies,
  domains,
  graphNodes,
  leads as seedLeads,
  projectMeta,
  quarantine,
  relations,
  snapshots,
  sources,
  tasks as seedTasks,
  trustedAssets,
  vendors,
} from "../data/dataset";
import type {
  Asset,
  AssetFilter,
  InvestigationTask,
  Lead,
  LeadStatus,
  LocalState,
  ReviewNote,
  Selection,
  ViewKey,
} from "../types";

const LS_KEY = "asm-workbench-local-v1";

const LEAD_STATUSES: LeadStatus[] = ["pending", "reviewed", "excluded"];
const TASK_STATUSES = new Set(["pending", "running", "partial-failed", "done", "failed"]);
const STAGE_STATUSES = new Set(["pending", "running", "done", "failed", "skipped"]);
const SUB_STATUSES = new Set(["pending", "running", "done", "failed", "retrying"]);

// ---------- 本地数据字段级校验 / 归一（坏数据不白屏） ----------

function cleanStr(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function normStages(v: unknown): InvestigationTask["stages"] | null {
  if (!Array.isArray(v)) return null;
  const out: InvestigationTask["stages"] = [];
  for (const s of v as Record<string, unknown>[]) {
    if (!s || typeof s !== "object") return null;
    const key = cleanStr(s.key);
    const name = cleanStr(s.name);
    const status = STAGE_STATUSES.has(s.status as string)
      ? (s.status as InvestigationTask["stages"][number]["status"])
      : null;
    if (!key || !name || !status) return null;
    out.push({
      key, name, status,
      started: cleanStr(s.started),
      finished: cleanStr(s.finished),
      resultCount: typeof s.resultCount === "number" ? s.resultCount : undefined,
    });
  }
  return out;
}

function normSubtasks(v: unknown): InvestigationTask["subtasks"] | null {
  if (!Array.isArray(v)) return null;
  const out: InvestigationTask["subtasks"] = [];
  for (const s of v as Record<string, unknown>[]) {
    if (!s || typeof s !== "object") return null;
    const id = cleanStr(s.id);
    const tool = cleanStr(s.tool);
    const status = SUB_STATUSES.has(s.status as string)
      ? (s.status as InvestigationTask["subtasks"][number]["status"])
      : null;
    if (!id || !tool || !status) return null;
    out.push({
      id, tool, status,
      durationSec: typeof s.durationSec === "number" ? s.durationSec : undefined,
      resultCount: typeof s.resultCount === "number" ? s.resultCount : undefined,
      failReason: cleanStr(s.failReason),
      log: Array.isArray(s.log) ? s.log.filter((x): x is string => typeof x === "string") : [],
    });
  }
  return out;
}

function normTask(v: unknown): InvestigationTask | null {
  if (!v || typeof v !== "object") return null;
  const t = v as Record<string, unknown>;
  const id = cleanStr(t.id);
  const name = cleanStr(t.name);
  const status = TASK_STATUSES.has(t.status as string)
    ? (t.status as InvestigationTask["status"])
    : null;
  const stages = normStages(t.stages);
  const subtasks = normSubtasks(t.subtasks);
  if (!id || !name || !status || !stages || !subtasks) return null;
  return {
    id,
    name,
    project: cleanStr(t.project) ?? "演示项目",
    mode: t.mode === "active" ? "active" : "passive",
    createdAt: cleanStr(t.createdAt) ?? new Date().toISOString(),
    status,
    stages,
    subtasks,
    tracks: Array.isArray(t.tracks)
      ? (t.tracks as Record<string, unknown>[]).flatMap((tr) =>
          tr && cleanStr(tr.key) && cleanStr(tr.name)
            ? [{ key: tr.key as string, name: tr.name as string, status: cleanStr(tr.status) ?? "" }]
            : []
        )
      : [],
  };
}

function normStrRecord(v: unknown): Record<string, string> {
  if (!v || typeof v !== "object") return {};
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v)) {
    if (typeof val === "string") out[k] = val;
  }
  return out;
}

function normLeadStatus(v: unknown): Record<string, LeadStatus> {
  if (!v || typeof v !== "object") return {};
  const out: Record<string, LeadStatus> = {};
  for (const [k, val] of Object.entries(v)) {
    if (LEAD_STATUSES.includes(val as LeadStatus)) out[k] = val as LeadStatus;
  }
  return out;
}

function normLeadNotes(v: unknown): Record<string, ReviewNote[]> {
  if (!v || typeof v !== "object") return {};
  const out: Record<string, ReviewNote[]> = {};
  for (const [k, val] of Object.entries(v)) {
    if (!Array.isArray(val)) continue;
    const notes = val.flatMap((n) => {
      if (!n || typeof n !== "object") return [];
      const rec = n as Record<string, unknown>;
      const text = cleanStr(rec.text);
      if (!text) return [];
      return [{ ts: cleanStr(rec.ts) ?? new Date().toISOString(), author: cleanStr(rec.author) ?? "演示分析员", text }];
    });
    if (notes.length) out[k] = notes;
  }
  return out;
}

function normHistory(v: unknown): Record<string, { ts: string; action: string }[]> {
  if (!v || typeof v !== "object") return {};
  const out: Record<string, { ts: string; action: string }[]> = {};
  for (const [k, val] of Object.entries(v)) {
    if (!Array.isArray(val)) continue;
    const items = val.flatMap((h) => {
      if (!h || typeof h !== "object") return [];
      const rec = h as Record<string, unknown>;
      const action = cleanStr(rec.action);
      if (!action) return [];
      return [{ ts: cleanStr(rec.ts) ?? new Date().toISOString(), action }];
    });
    if (items.length) out[k] = items;
  }
  return out;
}

function loadLocal(): LocalState {
  const fallback = defaultLocal();
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return fallback;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // 非法 JSON：清掉坏键，回退默认（可自愈）
      localStorage.removeItem(LS_KEY);
      return fallback;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      localStorage.removeItem(LS_KEY);
      return fallback;
    }
    const p = parsed as Record<string, unknown>;
    const demoTasks = Array.isArray(p.demoTasks)
      ? p.demoTasks.map(normTask).filter((t): t is InvestigationTask => t !== null)
      : [];
    const settings =
      p.settings && typeof p.settings === "object"
        ? { reduceMotion: !!(p.settings as Record<string, unknown>).reduceMotion }
        : fallback.settings;
    // 逐字段校验：缺失/非法字段回退默认，整批损坏时不会把异常带进视图层
    return {
      leadStatus: normLeadStatus(p.leadStatus),
      leadNotes: normLeadNotes(p.leadNotes),
      leadHistory: normHistory(p.leadHistory),
      demoTasks,
      settings,
    };
  } catch {
    return fallback;
  }
}

function defaultLocal(): LocalState {
  return {
    leadStatus: {},
    leadNotes: {},
    leadHistory: {},
    demoTasks: [],
    settings: { reduceMotion: false },
  };
}

function defaultAssetFilter(): AssetFilter {
  return {
    tab: "services",
    q: "",
    fCompany: "",
    fSource: "",
    fConf: "",
    fPort: "",
    fCdn: "",
    fLabel: "",
    sortKey: "lastSeen",
    sortAsc: false,
    page: 0,
    checked: [],
  };
}

export interface Store {
  // 静态演示数据（后端语义）
  companies: typeof companies;
  domains: typeof domains;
  assets: Asset[];
  trusted: Asset[];
  quarantine: typeof quarantine;
  leads: Lead[];
  tasks: InvestigationTask[];
  snapshots: typeof snapshots;
  sources: typeof sources;
  graphNodes: typeof graphNodes;
  relations: typeof relations;
  vendors: typeof vendors;
  project: typeof projectMeta;

  // 本地演示状态
  leadStatus: (id: string) => LeadStatus;
  leadNotes: (id: string) => ReviewNote[];
  leadHistory: (id: string) => { ts: string; action: string }[];
  setLeadStatus: (id: string, s: LeadStatus) => void;
  addLeadNote: (id: string, text: string) => void;

  // 任务模拟（仅演示）
  advanceTask: (id: string) => void;
  retrySubtask: (taskId: string, subId: string) => void;
  createDemoTask: (t: InvestigationTask) => void;

  // 资产探索筛选状态（跨视图保留；仅会话内存，不持久化）
  assetFilter: AssetFilter;
  setAssetFilter: (patch: Partial<AssetFilter>) => void;

  // 导航与选中
  selection: Selection;
  navigate: (view: ViewKey, patch?: Partial<Selection>) => void;
  pushTrail: (label: string, kind: Selection["trail"][number]["kind"], refId?: string) => void;
  popTrailTo: (index: number) => void;
  openAsset: (assetKey: string) => void;
  openDomain: (domain: string) => void;
  openLead: (leadId: string) => void;
  clearSelection: () => void;

  // 演示重置
  resetDemo: () => void;
  reduceMotion: boolean;
  setReduceMotion: (v: boolean) => void;
}

const StoreCtx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(StoreCtx);
  if (!s) throw new Error("StoreProvider missing");
  return s;
}

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [local, setLocal] = useState<LocalState>(loadLocal);
  const persistTimer = useRef<number | null>(null);

  const persist = useCallback((next: LocalState) => {
    setLocal(next);
    if (persistTimer.current) window.clearTimeout(persistTimer.current);
    persistTimer.current = window.setTimeout(() => {
      try {
        localStorage.setItem(LS_KEY, JSON.stringify(next));
      } catch {
        /* 存储不可用时静默降级 */
      }
    }, 120);
  }, []);

  const [selection, setSelection] = useState<Selection>({
    view: new URLSearchParams(window.location.search).get("pilot") === "1" ? "pilot" : "overview",
    trail: [{ label: new URLSearchParams(window.location.search).get("pilot") === "1" ? "被动试点" : "项目概览", kind: "view" }],
  });

  // 资产探索筛选状态：提升到 store，切换视图再返回时保留（仅会话内存）
  const [assetFilter, setAssetFilterState] = useState<AssetFilter>(defaultAssetFilter());
  const setAssetFilter = useCallback((patch: Partial<AssetFilter>) => {
    setAssetFilterState((prev) => ({ ...prev, ...patch }));
  }, []);

  const navigate = useCallback((view: ViewKey, patch: Partial<Selection> = {}) => {
    const labels: Record<ViewKey, string> = {
      overview: "项目概览",
      assets: "资产探索",
      tasks: "调查任务",
      review: "证据复核",
      graph: "关系图谱",
      sources: "数据来源",
      reports: "报告中心",
      pilot: "被动试点",
    };
    setSelection((prev) => ({
      view,
      assetKey: patch.assetKey,
      domain: patch.domain,
      leadId: patch.leadId,
      taskId: patch.taskId,
      trail: patch.trail ?? [{ label: labels[view], kind: "view" as const }],
    }));
  }, []);

  const pushTrail = useCallback(
    (label: string, kind: Selection["trail"][number]["kind"], refId?: string) => {
      setSelection((prev) => {
        const last = prev.trail[prev.trail.length - 1];
        if (last && last.label === label && last.refId === refId) return prev;
        return { ...prev, trail: [...prev.trail, { label, kind, refId }] };
      });
    },
    []
  );

  const popTrailTo = useCallback((index: number) => {
    setSelection((prev) => {
      const trail = prev.trail.slice(0, index + 1);
      const keepAsset = trail.some((t) => t.kind === "asset");
      return {
        ...prev,
        trail,
        assetKey: keepAsset ? prev.assetKey : undefined,
      };
    });
  }, []);

  const openAsset = useCallback((assetKey: string) => {
    setSelection((prev) => ({
      ...prev,
      assetKey,
      trail: [
        ...prev.trail.filter((t) => t.kind !== "asset" && t.kind !== "evidence"),
        { label: assetKey.split("|")[0] + ":" + assetKey.split("|")[1], kind: "asset", refId: assetKey },
      ],
    }));
  }, []);

  const openDomain = useCallback((domain: string) => {
    setSelection((prev) => ({
      ...prev,
      view: "assets",
      domain,
      trail: [
        { label: "资产探索", kind: "view" as const },
        { label: domain, kind: "domain" as const, refId: domain },
      ],
    }));
  }, []);

  const openLead = useCallback((leadId: string) => {
    setSelection((prev) => ({
      ...prev,
      view: "review",
      leadId,
      trail: [
        { label: "证据复核", kind: "view" as const },
        { label: leadId, kind: "evidence" as const, refId: leadId },
      ],
    }));
  }, []);

  const clearSelection = useCallback(() => {
    setSelection((prev) => ({ ...prev, assetKey: undefined }));
  }, []);

  // ---------- 线索本地状态 ----------

  const leadStatus = useCallback(
    (id: string): LeadStatus => local.leadStatus[id] ?? "pending",
    [local]
  );
  const leadNotes = useCallback(
    (id: string) => local.leadNotes[id] ?? [],
    [local]
  );
  const leadHistory = useCallback(
    (id: string) => local.leadHistory[id] ?? [],
    [local]
  );

  const recordHistory = (l: LocalState, id: string, action: string): LocalState => ({
    ...l,
    leadHistory: {
      ...l.leadHistory,
      [id]: [
        ...(l.leadHistory[id] ?? []),
        { ts: new Date().toISOString(), action },
      ],
    },
  });

  const setLeadStatus = useCallback(
    (id: string, s: LeadStatus) => {
      const label = { pending: "标记待复核", reviewed: "标记已复核", excluded: "标记排除" }[s];
      persist(recordHistory({ ...local, leadStatus: { ...local.leadStatus, [id]: s } }, id, label));
    },
    [local, persist]
  );

  const addLeadNote = useCallback(
    (id: string, text: string) => {
      const note: ReviewNote = {
        ts: new Date().toISOString(),
        author: "演示分析员",
        text,
      };
      const next = {
        ...local,
        leadNotes: { ...local.leadNotes, [id]: [...(local.leadNotes[id] ?? []), note] },
      };
      persist(recordHistory(next, id, "添加备注"));
    },
    [local, persist]
  );

  // ---------- 任务模拟（仅演示，不执行真实扫描） ----------

  // 合并时按 id 去重：演示任务覆盖同 id 种子任务，避免列表出现两张同 run 卡片
  const allTasks = useMemo(() => {
    const merged = new Map<string, InvestigationTask>();
    for (const t of seedTasks) merged.set(t.id, t);
    for (const t of local.demoTasks) merged.set(t.id, t);
    return [...merged.values()];
  }, [local.demoTasks]);

  // 阶段 ↔ 工具子任务的演示同步：推进/重试时子任务一并跟进，不留悬挂
  const STAGE_SUBTASK: Record<string, string[]> = {
    s4: ["st1"],
    s5: ["st2"],
    s6: ["st3"],
    s7: ["st4", "st5"],
    s8: ["st6"],
  };

  const advanceTask = useCallback(
    (id: string) => {
      const apply = (t: InvestigationTask): InvestigationTask => {
        const stages = t.stages.map((s) => ({ ...s }));
        const running = stages.findIndex((s) => s.status === "running");
        const failed = stages.findIndex((s) => s.status === "failed");
        const idx = failed >= 0 ? failed : running;
        if (idx < 0) return t;
        const now = new Date().toISOString();
        stages[idx] = { ...stages[idx], status: "done", finished: now, resultCount: stages[idx].resultCount ?? 1 };
        if (idx + 1 < stages.length) {
          stages[idx + 1] = { ...stages[idx + 1], status: "running", started: now };
        }
        // 同步子任务：完成阶段的失败/进行中子任务标记完成（模拟重试成功），下一阶段子任务转运行
        const completedSubIds = new Set(STAGE_SUBTASK[stages[idx].key] ?? []);
        const nextSubIds = new Set(idx + 1 < stages.length ? STAGE_SUBTASK[stages[idx + 1].key] ?? [] : []);
        const subtasks = t.subtasks.map((st) => {
          if (completedSubIds.has(st.id) && (st.status === "failed" || st.status === "running" || st.status === "retrying")) {
            return {
              ...st,
              status: "done" as const,
              failReason: undefined,
              resultCount: (st.resultCount ?? 0) + (st.status === "failed" ? 3 : 0),
              log: [...st.log, `[模拟] ${new Date().toLocaleTimeString("zh-CN")} 阶段重跑完成`],
            };
          }
          if (nextSubIds.has(st.id) && st.status === "pending") {
            return {
              ...st,
              status: "running" as const,
              log: [...st.log, `[模拟] ${new Date().toLocaleTimeString("zh-CN")} 开始执行`],
            };
          }
          return st;
        });
        const anyFailed = stages.some((s) => s.status === "failed");
        const done = stages.every((s) => s.status === "done" || s.status === "skipped");
        return { ...t, stages, status: anyFailed ? "partial-failed" : done ? "done" : "running", subtasks };
      };
      persist({
        ...local,
        demoTasks: upsertTask(local.demoTasks, allTasks, id, apply),
      });
    },
    [local, persist, allTasks]
  );

  const retrySubtask = useCallback(
    (taskId: string, subId: string) => {
      const apply = (t: InvestigationTask): InvestigationTask => ({
        ...t,
        status: "running",
        subtasks: t.subtasks.map((st) =>
          st.id === subId && (st.status === "failed" || st.status === "retrying")
            ? {
                ...st,
                status: "done",
                failReason: undefined,
                resultCount: (st.resultCount ?? 0) + 3,
                log: [...st.log, `[模拟] ${new Date().toLocaleTimeString("zh-CN")} 重试成功，补采 3 个目标`],
              }
            : st
        ),
      });
      persist({
        ...local,
        demoTasks: upsertTask(local.demoTasks, allTasks, taskId, apply),
      });
    },
    [local, persist, allTasks]
  );

  const createDemoTask = useCallback(
    (t: InvestigationTask) => {
      persist({ ...local, demoTasks: [t, ...local.demoTasks] });
    },
    [local, persist]
  );

  const resetDemo = useCallback(() => {
    try {
      localStorage.removeItem(LS_KEY);
    } catch {
      /* ignore */
    }
    setLocal(defaultLocal());
    setAssetFilterState(defaultAssetFilter());
    setSelection({
      view: "overview",
      trail: [{ label: "项目概览", kind: "view" }],
    });
  }, []);

  const trusted = useMemo(() => trustedAssets(seedAssets), []);

  const store: Store = {
    companies,
    domains,
    assets: seedAssets,
    trusted,
    quarantine,
    leads: seedLeads,
    tasks: allTasks,
    snapshots,
    sources,
    graphNodes,
    relations,
    vendors,
    project: projectMeta,
    leadStatus,
    leadNotes,
    leadHistory,
    setLeadStatus,
    addLeadNote,
    advanceTask,
    retrySubtask,
    createDemoTask,
    selection,
    navigate,
    pushTrail,
    popTrailTo,
    openAsset,
    openDomain,
    openLead,
    clearSelection,
    resetDemo,
    assetFilter,
    setAssetFilter,
    reduceMotion: local.settings.reduceMotion,
    setReduceMotion: (v) =>
      persist({ ...local, settings: { ...local.settings, reduceMotion: v } }),
  };

  return <StoreCtx.Provider value={store}>{children}</StoreCtx.Provider>;
}

function upsertTask(
  demoTasks: InvestigationTask[],
  allTasks: InvestigationTask[],
  id: string,
  apply: (t: InvestigationTask) => InvestigationTask
): InvestigationTask[] {
  const existing = allTasks.find((t) => t.id === id);
  if (!existing) return demoTasks;
  const updated = apply(existing);
  const rest = demoTasks.filter((t) => t.id !== id);
  return [updated, ...rest];
}

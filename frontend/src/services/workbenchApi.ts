export type JsonObject = Record<string, any>;

export interface ModeCatalog {
  schema_version: number;
  presets: Record<string, JsonObject>;
  capability_catalog: Record<string, JsonObject>;
  defaults?: JsonObject;
  [key: string]: any;
}

export interface RunRecord {
  run_id: string;
  project_id: string;
  status: string;
  config: JsonObject;
  directory: string;
  steps?: JsonObject[];
  assets?: JsonObject[];
  snapshot?: JsonObject;
  [key: string]: any;
}

export interface ProjectRecord {
  project_id: string;
  purpose?: "investigation" | "validation" | "demo";
  name?: string;
  path?: string;
  revision?: string | number;
  config?: JsonObject;
  runs?: JsonObject[];
  [key: string]: any;
}

export interface RunEvent {
  id: string;
  kind: string;
  data: JsonObject;
  ts: string;
}

export interface Artifact {
  path: string;
  bytes: number;
}

const base = (import.meta.env.VITE_ASM_API_URL || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    cache: "no-store",
  });
  const text = await response.text();
  let payload: any;
  try { payload = text ? JSON.parse(text) : null; }
  catch { throw new ApiError(`后端返回了不可解析的响应（HTTP ${response.status}）`, response.status); }
  if (!response.ok) {
    throw new ApiError(String(payload?.error || payload?.detail || payload?.message || `HTTP ${response.status}`), response.status);
  }
  return payload as T;
}

const encode = encodeURIComponent;
export const workbenchApi = {
  modes: () => request<ModeCatalog>("/modes"),
  projects: async () => {
    const result = await request<ProjectRecord[] | { projects: ProjectRecord[] }>("/projects?purpose=all");
    return Array.isArray(result) ? result : result.projects;
  },
  create: (config: JsonObject) => request<ProjectRecord>("/projects", { method: "POST", body: JSON.stringify(config) }),
  config: (id: string) => request<{ project_id: string; path: string; revision: string | number; config: JsonObject }>(`/projects/${encode(id)}/config`),
  saveConfig: (id: string, config: JsonObject) => request<JsonObject>(`/projects/${encode(id)}/config`, { method: "PUT", body: JSON.stringify(config) }),
  start: (id: string) => request<RunRecord>(`/projects/${encode(id)}/start`, { method: "POST", body: "{}" }),
  run: (id: string) => request<RunRecord | null>(`/projects/${encode(id)}/run`),
  runState: (id: string) => request<RunRecord>(`/runs/${encode(id)}/state`),
  control: (id: string, action: "pause" | "resume" | "stop" | "export") => request<JsonObject>(`/runs/${encode(id)}/${action}`, { method: "POST", body: "{}" }),
  scope: (id: string, value: string) => request<JsonObject>(`/projects/${encode(id)}/scope`, { method: "POST", body: JSON.stringify({ value }) }),
  artifacts: async (id: string) => {
    const result = await request<Artifact[] | { artifacts: Artifact[] }>(`/runs/${encode(id)}/artifacts`);
    return Array.isArray(result) ? result : result.artifacts;
  },
  fileUrl: (id: string, path: string) => `${base}/runs/${encode(id)}/content/${path.replace(/\\/g, "/").split("/").map(encode).join("/")}`,
  toolCalls: async (id: string): Promise<JsonObject[]> => {
    const response = await fetch(`${base}/runs/${encode(id)}/files?path=${encode("logs/tool-calls.jsonl")}`, { cache: "no-store" });
    if (response.status === 404) return [];
    if (!response.ok) throw new ApiError(`工具日志读取失败（HTTP ${response.status}）`, response.status);
    const lines = (await response.text()).split(/\r?\n/).filter(line => line.trim());
    return lines.map((line, index) => {
      try { return JSON.parse(line); }
      catch { throw new ApiError(`磁盘工具日志第 ${index + 1} 行不可解析`, 500); }
    });
  },
  preview: async (id: string, path: string) => {
    const response = await fetch(`${base}/runs/${encode(id)}/files?path=${encode(path)}`, { cache: "no-store" });
    if (!response.ok) throw new ApiError(`文件预览失败（HTTP ${response.status}）`, response.status);
    // Evidence may contain large output. The preview is bounded and rendered as text.
    const reader = response.body?.getReader();
    if (!reader) return "";
    const decoder = new TextDecoder();
    let result = "";
    let size = 0;
    try {
      while (size < 65536) {
        const part = await reader.read();
        if (part.done) break;
        size += part.value.length;
        result += decoder.decode(part.value, { stream: true });
      }
      result += decoder.decode();
      return result.slice(0, 65536) + (size >= 65536 ? "\n…预览已截断，请下载完整文件。" : "");
    } finally { await reader.cancel(); }
  },
  plan: (id: string) => request<JsonObject>(`/projects/${encode(id)}/plan`),
  bundle: (id: string, snapshotId: string) => request<JsonObject>(`/runs/${encode(id)}/bundle`, { method: "POST", body: JSON.stringify({ snapshot_id: snapshotId }) }),
  review: (id: string, decision: JsonObject) => request<JsonObject>(`/runs/${encode(id)}/review`, { method: "POST", body: JSON.stringify(decision) }),
  settings: () => request<JsonObject>("/settings"),
  saveSettings: (credentials: Record<string, string>) => request<JsonObject>("/settings", { method: "PUT", body: JSON.stringify({ credentials }) }),
};

export function subscribeRun(
  runId: string,
  onEvent: (event: RunEvent) => void,
  onConnection: (state: "connecting" | "connected" | "disconnected") => void,
): () => void {
  const controller = new AbortController();
  const cursorKey = `asm-workbench:event-cursor:${runId}`;
  let cursor = "";
  try { cursor = localStorage.getItem(cursorKey) || ""; } catch { /* Storage may be disabled. */ }
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let backoff = 1000;

  const deliver = (block: string) => {
    let eventId = "";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("id:")) eventId = line.slice(3).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    try {
      const event = JSON.parse(data.join("\n")) as RunEvent;
      event.id = String(event.id || eventId);
      if (!event.id) return;
      cursor = event.id;
      try { localStorage.setItem(cursorKey, cursor); } catch { /* Only a non-secret cursor is persisted. */ }
      onEvent(event);
    } catch { /* A malformed event is not displayed as a valid tool result. */ }
  };

  const connect = async () => {
    if (controller.signal.aborted) return;
    onConnection("connecting");
    try {
      const response = await fetch(`${base}/runs/${encode(runId)}/events`, {
        signal: controller.signal, cache: "no-store",
        headers: { Accept: "text/event-stream", ...(cursor ? { "Last-Event-ID": cursor } : {}) },
      });
      if (!response.ok || !response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
        throw new ApiError("事件流不可用", response.status);
      }
      onConnection("connected");
      backoff = 1000;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!controller.signal.aborted) {
          const part = await reader.read();
          if (part.done) break;
          buffer += decoder.decode(part.value, { stream: true }).replace(/\r\n/g, "\n");
          let boundary: number;
          while ((boundary = buffer.indexOf("\n\n")) >= 0) {
            deliver(buffer.slice(0, boundary));
            buffer = buffer.slice(boundary + 2);
          }
        }
      } finally { await reader.cancel().catch(() => undefined); }
    } catch (error) {
      if (controller.signal.aborted) return;
    }
    if (!controller.signal.aborted) {
      onConnection("disconnected");
      retryTimer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 10000);
    }
  };
  void connect();
  return () => { controller.abort(); if (retryTimer) clearTimeout(retryTimer); };
}

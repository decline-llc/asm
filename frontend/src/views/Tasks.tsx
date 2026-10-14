import React, { useMemo, useState } from "react";
import { useStore } from "../services/store";
import type { InvestigationTask } from "../types";
import { Badge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";
import { useFocusTrap } from "../components/useFocusTrap";

const STAGE_NAMES = [
  "种子标准化", "股权穿透与ICP备案", "范围确认", "子域名收集",
  "DNS/CDN 分析", "端口服务发现", "Web 识别与截图", "报告生成",
];

export function Tasks({ wizardOpen, setWizardOpen }: { wizardOpen: boolean; setWizardOpen: (v: boolean) => void }) {
  const { tasks, selection, navigate, advanceTask, retrySubtask } = useStore();
  const current = selection.taskId
    ? tasks.find((t) => t.id === selection.taskId)
    : undefined;

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>调查任务</h2>
        <span className="desc">顺序执行；「暂停 / 终止」暂无可靠后端能力，展示为禁用</span>
        <button className="btn primary" style={{ marginLeft: "auto" }} onClick={() => setWizardOpen(true)}>
          <Icon name="plus" size={14} /> 新建调查（演示）
        </button>
      </div>

      {!current && (
        <div className="grid cols-3">
          {tasks.map((t) => (
            <TaskCard key={t.id} task={t} onOpen={() => navigate("tasks", { taskId: t.id })} />
          ))}
        </div>
      )}

      {current && (
        <TaskDetail
          task={current}
          onBack={() => navigate("tasks")}
          onAdvance={() => advanceTask(current.id)}
          onRetry={(subId) => retrySubtask(current.id, subId)}
        />
      )}

      {wizardOpen && <TaskWizard onClose={() => setWizardOpen(false)} />}
    </div>
  );
}

function TaskCard({ task, onOpen }: { task: InvestigationTask; onOpen: () => void }) {
  const done = task.stages.filter((s) => s.status === "done").length;
  const tone =
    task.status === "done" ? "ok" : task.status === "partial-failed" ? "warn" : task.status === "failed" ? "danger" : "info";
  return (
    <button className="panel lead-item" style={{ display: "block", textAlign: "left" }} onClick={onOpen}>
      <div className="row1">
        <Badge tone={tone as "ok" | "warn" | "danger" | "info"}>
          {{ done: "已完成", "partial-failed": "部分失败", failed: "失败", running: "进行中", pending: "排队中" }[task.status]}
        </Badge>
        <Badge tone="neutral">{task.mode === "passive" ? "被动" : "主动"}</Badge>
        {task.id.startsWith("DEMO") && <Badge tone="demo">演示任务</Badge>}
      </div>
      <div className="target" style={{ fontFamily: "var(--sans)", fontWeight: 600 }}>{task.name}</div>
      <div className="reason">
        <span className="mono">{task.id}</span> · 创建于 {task.createdAt.replace("T", " ").replace("Z", "")}
      </div>
      <div style={{ marginTop: 8, height: 5, borderRadius: 3, background: "var(--border)" }}>
        <div
          style={{
            height: "100%",
            width: `${(done / task.stages.length) * 100}%`,
            borderRadius: 3,
            background: task.status === "partial-failed" ? "var(--amber)" : "var(--accent)",
            transition: "width var(--speed)",
          }}
        />
      </div>
      <div className="reason" style={{ marginTop: 5 }}>
        {done}/{task.stages.length} 阶段完成{task.status === "running" && " · 正在处理，总量未知时不预估剩余时间"}
      </div>
    </button>
  );
}

function TaskDetail({
  task,
  onBack,
  onAdvance,
  onRetry,
}: {
  task: InvestigationTask;
  onBack: () => void;
  onAdvance: () => void;
  onRetry: (subId: string) => void;
}) {
  const unfinished = task.stages.some((s) => s.status === "running" || s.status === "failed");
  return (
    <div>
      <button className="btn small ghost" onClick={onBack}>← 返回任务列表</button>
      <div className="panel" style={{ marginTop: 10 }}>
        <div className="panel-head">
          <h3>{task.name}</h3>
          <span className="mono hint">{task.id}</span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            {unfinished && (
              <button className="btn primary small" onClick={onAdvance}>
                <Icon name="refresh" size={13} /> 模拟推进一阶段
              </button>
            )}
            <button className="btn small" disabled title="后端尚无可靠的暂停能力，展示为禁用，不承诺真实控制">
              暂停（待后端支持）
            </button>
            <button className="btn small" disabled title="后端尚无可靠的终止能力，展示为禁用，不承诺真实控制">
              终止（待后端支持）
            </button>
          </div>
        </div>
        <div className="panel-body">
          <div className="notice info">
            <Icon name="task" size={14} />
            本任务运行于演示模式：不执行真实扫描，不调用第三方 API，浏览器未连接 WSL 执行层。
          </div>

          <h4 style={{ margin: "4px 0 10px", fontSize: 13 }}>阶段流程</h4>
          <div className="pipeline" style={{ marginBottom: 16 }}>
            {task.stages.map((s, i) => (
              <div className="step" key={s.key}>
                {i > 0 && <span className="arrow" />}
                <span
                  className={`node ${s.status === "done" ? "done" : s.status === "failed" ? "warn" : ""}`}
                  title={s.resultCount != null ? `结果 ${s.resultCount} 条` : undefined}
                >
                  {s.status === "done" && "✓ "}
                  {s.status === "failed" && "✕ "}
                  {s.status === "running" && "● "}
                  {s.name}
                  {s.resultCount != null && <span style={{ color: "var(--ink-3)" }}>（{s.resultCount}）</span>}
                </span>
              </div>
            ))}
          </div>

          <h4 style={{ margin: "0 0 10px", fontSize: 13 }}>工具子任务</h4>
          <table className="data">
            <thead>
              <tr><th>工具</th><th>状态</th><th>耗时</th><th>结果数</th><th>失败原因</th><th>操作</th></tr>
            </thead>
            <tbody>
              {task.subtasks.map((st) => (
                <tr key={st.id} style={{ cursor: "default" }}>
                  <td className="mono">{st.tool}</td>
                  <td>
                    <Badge tone={st.status === "done" ? "ok" : st.status === "failed" ? "danger" : st.status === "running" ? "info" : "neutral"}>
                      {{ done: "完成", failed: "失败", running: "运行中", pending: "等待", retrying: "重试中" }[st.status]}
                    </Badge>
                  </td>
                  <td className="num">{st.durationSec != null ? `${st.durationSec}s` : "—"}</td>
                  <td className="num">{st.resultCount ?? "—"}</td>
                  <td style={{ color: "var(--red)", fontSize: 12 }}>{st.failReason ?? "—"}</td>
                  <td>
                    {st.status === "failed" && (
                      <button className="btn small" onClick={() => onRetry(st.id)}>
                        <Icon name="refresh" size={12} /> 重试（模拟）
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4 style={{ margin: "16px 0 10px", fontSize: 13 }}>线索轨道（顺序执行）</h4>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            {task.tracks.map((tr) => (
              <span key={tr.key} className="chip" style={{ borderRadius: 8 }}>
                {tr.name}：{tr.status}
              </span>
            ))}
          </div>

          <h4 style={{ margin: "0 0 10px", fontSize: 13 }}>日志（文本安全渲染）</h4>
          {task.subtasks.map((st) => (
            <div key={st.id} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 4 }} className="mono">
                ── {st.tool}
              </div>
              <div className="log-box">{st.log.join("\n")}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** 四步新建调查向导（创建演示任务）；支持 Esc 关闭与焦点圈定 */
function TaskWizard({ onClose }: { onClose: () => void }) {
  const { project, companies, createDemoTask, navigate } = useStore();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"passive" | "active">("passive");
  const [seed, setSeed] = useState("example.com");
  const [exclusions, setExclusions] = useState<string[]>(["云帆 SaaS（非目标资产）"]);
  const [stages, setStages] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]));
  const [err, setErr] = useState("");
  // 焦点圈定 + Esc 关闭 + 关闭后焦点恢复触发按钮
  const wizardRef = useFocusTrap<HTMLDivElement>({ onClose });

  const toggleStage = (i: number) => {
    const next = new Set(stages);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setStages(next);
  };

  const next = () => {
    if (step === 0 && !seed.trim()) return setErr("请至少填写一个根域名或种子");
    if (step === 2 && stages.size === 0) return setErr("请至少选择一个采集阶段");
    setErr("");
    setStep(step + 1);
  };

  const create = () => {
    const id = `DEMO-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}-${String(Math.floor(Math.random() * 900) + 100)}`;
    const task: InvestigationTask = {
      id,
      name: `${project.name} · ${mode === "passive" ? "被动" : "主动"}演示调查`,
      project: project.name,
      mode,
      createdAt: new Date().toISOString(),
      status: "running",
      // 阶段键与主任务一致（s1..s8），子任务 id 用 st1..st6，使「模拟推进」能同步子任务状态
      stages: STAGE_NAMES.map((name, i) => ({
        key: `s${i + 1}`,
        name,
        status: stages.has(i) ? (i === Math.min(...stages) ? "running" : "pending") : "skipped",
        started: i === Math.min(...stages) && stages.has(i) ? new Date().toISOString() : undefined,
      })),
      subtasks: [
        { id: "st1", tool: "oneforall", status: "running", log: ["[模拟] 演示任务已创建，等待推进…"] },
        { id: "st2", tool: "dnsx/dig", status: "pending", log: ["等待 DNS 阶段"] },
        { id: "st3", tool: "nmap", status: "pending", log: ["等待端口扫描阶段（nmap）"] },
        { id: "st4", tool: "httpx (Windows)", status: "pending", log: ["等待 Web 探测阶段"] },
        { id: "st5", tool: "playwright-截图", status: "pending", log: ["等待截图阶段（Windows Playwright）"] },
        { id: "st6", tool: "report", status: "pending", log: ["等待报告阶段"] },
      ],
      tracks: [
        { key: "main", name: "主流程（顺序执行）", status: "进行中（模拟）" },
        { key: "p1", name: "P1 OSINT 线索", status: "未启用" },
        { key: "p2", name: "P2 供应链线索", status: "未启用" },
      ],
    };
    createDemoTask(task);
    onClose();
    navigate("tasks", { taskId: id });
  };

  const stepTitles = ["项目与种子", "范围与排除项", "模式与阶段", "摘要确认"];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div ref={wizardRef} className="modal" role="dialog" aria-modal="true" aria-label="新建调查向导" tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 style={{ margin: 0, fontSize: 15 }}>新建调查（演示任务）</h3>
          <button className="drawer-close" style={{ marginLeft: "auto" }} onClick={onClose} aria-label="关闭">
            <Icon name="close" size={16} />
          </button>
        </div>
        <div className="modal-body">
          <div className="wizard-steps">
            {stepTitles.map((t, i) => (
              <div key={t} className={`wstep ${i === step ? "active" : i < step ? "done" : ""}`}>
                {i + 1}. {t}
              </div>
            ))}
          </div>

          {err && <div className="notice danger"><Icon name="warn" size={14} />{err}</div>}

          {step === 0 && (
            <>
              <dl className="fields">
                <dt>项目</dt>
                <dd>{project.name}（当前演示项目，切换项目待后端支持）</dd>
              </dl>
              <label style={{ display: "block", marginTop: 12, fontSize: 12.5, fontWeight: 600 }}>
                种子（根域名 / 公司名 / IP 段，逗号分隔）
              </label>
              <input
                type="text"
                style={{ width: "100%", marginTop: 6, padding: "7px 10px", border: "1px solid var(--border-strong)", borderRadius: 8 }}
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
              <div className="notice info" style={{ marginTop: 10 }}>
                <Icon name="evidence" size={14} />
                股权穿透可发现 {companies.length - 1} 家关联企业；股权关系不会自动等价于授权范围。
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <h4 style={{ margin: "0 0 8px", fontSize: 13 }}>纳入范围</h4>
              <table className="data">
                <thead><tr><th>类型</th><th>对象</th><th>依据</th></tr></thead>
                <tbody>
                  <tr style={{ cursor: "default" }}><td>公司</td><td>{project.name}</td><td>种子主体</td></tr>
                  <tr style={{ cursor: "default" }}><td>根域名</td><td className="mono">{seed}</td><td>ICP 备案主体一致</td></tr>
                  {project.seeds.ipRanges.map((r) => (
                    <tr key={r} style={{ cursor: "default" }}><td>IP/CIDR</td><td className="mono">{r}</td><td>客户提供</td></tr>
                  ))}
                </tbody>
              </table>
              <h4 style={{ margin: "14px 0 8px", fontSize: 13 }}>排除项与理由</h4>
              {["云帆 SaaS（非目标资产）", "198.18.0.0/15 假地址观测段"].map((ex) => (
                <label key={ex} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0", fontSize: 12.8 }}>
                  <input
                    type="checkbox"
                    checked={exclusions.includes(ex)}
                    onChange={(e) =>
                      setExclusions(e.target.checked ? [...exclusions, ex] : exclusions.filter((x) => x !== ex))
                    }
                  />
                  {ex}
                  <span style={{ color: "var(--ink-3)", fontSize: 11.5 }}>
                    {ex.includes("SaaS") ? "— SaaS 承载业务但非目标资产" : "— 异常观测段，不可扫描"}
                  </span>
                </label>
              ))}
            </>
          )}

          {step === 2 && (
            <>
              <h4 style={{ margin: "0 0 8px", fontSize: 13 }}>采集模式</h4>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "6px 0" }}>
                <input type="radio" checked={mode === "passive"} onChange={() => setMode("passive")} />
                <span>
                  <b>被动模式（默认）</b>
                  <div style={{ fontSize: 12, color: "var(--ink-3)" }}>仅第三方数据与公开观测，不主动触达目标</div>
                </span>
              </label>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start", padding: "6px 0", opacity: 0.75 }}>
                <input type="radio" checked={mode === "active"} onChange={() => setMode("active")} />
                <span>
                  <b>主动模式</b>
                  <div style={{ fontSize: 12, color: "var(--amber)" }}>
                    需配置 authorization: true 与白名单；当前演示项目未授权，仅展示约束说明
                  </div>
                </span>
              </label>
              <h4 style={{ margin: "14px 0 8px", fontSize: 13 }}>采集阶段</h4>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                {STAGE_NAMES.map((s, i) => (
                  <label key={s} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12.8, padding: "3px 0" }}>
                    <input type="checkbox" checked={stages.has(i)} onChange={() => toggleStage(i)} />
                    {s}
                    {mode === "passive" && (i === 5 || i === 6) && (
                      <span style={{ fontSize: 11, color: "var(--amber)" }}>（被动模式下降级为回放/探测已有结果）</span>
                    )}
                  </label>
                ))}
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <dl className="fields">
                <dt>项目</dt><dd>{project.name}</dd>
                <dt>种子</dt><dd className="mono">{seed}</dd>
                <dt>模式</dt><dd>{mode === "passive" ? "被动" : "主动（未授权，仅演示）"}</dd>
                <dt>阶段</dt><dd>{[...stages].sort().map((i) => STAGE_NAMES[i]).join("、")}</dd>
                <dt>排除项</dt><dd>{exclusions.join("；") || "无"}</dd>
                <dt>行为说明</dt>
                <dd>创建的是<b>演示任务</b>：可模拟推进、部分失败与重试；不执行真实扫描，不调用第三方 API。</dd>
              </dl>
            </>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
            {step > 0 && <button className="btn" onClick={() => setStep(step - 1)}>上一步</button>}
            <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button className="btn" onClick={onClose}>取消</button>
              {step < 3 ? (
                <button className="btn primary" onClick={next}>下一步</button>
              ) : (
                <button className="btn primary" onClick={create}>创建演示任务</button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

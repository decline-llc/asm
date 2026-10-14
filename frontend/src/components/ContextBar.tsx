import React, { useState } from "react";
import { useStore } from "../services/store";
import { Icon } from "./Icons";

/** 紧凑上下文条：项目 / run_id / 采集模式 / 范围摘要，可展开 */
export function ContextBar() {
  const { project } = useStore();
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="context-bar" role="status">
        <span className="item">
          项目 <b>{project.name}</b>
        </span>
        <span className="item">
          run_id <b className="mono">{project.currentRun}</b>
        </span>
        <span className="item">
          模式 <b>{project.mode === "passive" ? "被动采集" : "主动采集"}</b>
        </span>
        <span className="item">
          范围 <b>{project.seeds.rootDomains.join("、")}</b> ·{" "}
          {project.seeds.ipRanges.length} 个 IP 段
        </span>
        <button className="toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "收起范围" : "展开范围与排除项"}
          <Icon name="chevron" size={12} />
        </button>
      </div>
      {open && (
        <div className="context-detail">
          <div>
            <dt>纳入根域名</dt>
            <dd className="mono">{project.seeds.rootDomains.join("，")}</dd>
          </div>
          <div>
            <dt>纳入 IP/CIDR</dt>
            <dd className="mono">{project.seeds.ipRanges.join("，")}</dd>
          </div>
          <div>
            <dt>排除项</dt>
            <dd>{project.exclusions.join("；")}</dd>
          </div>
          <div>
            <dt>说明</dt>
            <dd>范围经 Stage 3 人工确认；股权关系不自动等价于授权范围。</dd>
          </div>
        </div>
      )}
    </>
  );
}

import React, { useState } from "react";
import { useStore } from "../services/store";
import { Icon } from "./Icons";
import { SearchModal } from "./SearchModal";

export function TopBar({ onNewTask }: { onNewTask: () => void }) {
  const { project, tasks } = useStore();
  const [searchOpen, setSearchOpen] = useState(false);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const running = tasks.find((t) => t.status === "running" || t.status === "partial-failed");

  return (
    <header className="topbar">
      <div className="project">
        <Icon name="building" size={17} />
        {project.name}
      </div>
      <button
        className="search-trigger"
        onClick={() => setSearchOpen(true)}
        aria-label="全局搜索（Ctrl+K）"
      >
        <Icon name="search" size={14} />
        搜索企业 / 域名 / IP / 服务 / 任务…
        <kbd>Ctrl K</kbd>
      </button>
      <div className="meta">
        <span className="hide-s" title="最近一次运行完成时间">
          <Icon name="clock" size={13} /> 最近运行{" "}
          <span className="mono">{project.lastRunAt.replace("T", " ").replace("Z", "")}</span>
        </span>
        {running && (
          <span className="hide-s badge info" title={running.id}>
            ● {running.name}
          </span>
        )}
        <span className="demo-pill" title="所有数据为本地演示数据，未连接后端">
          演示数据
        </span>
        <button className="btn primary small" onClick={onNewTask}>
          <Icon name="plus" size={13} />
          新建调查
        </button>
      </div>
      {searchOpen && <SearchModal onClose={() => setSearchOpen(false)} />}
    </header>
  );
}

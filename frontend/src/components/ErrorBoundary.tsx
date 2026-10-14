import React from "react";
import { Icon } from "./Icons";

interface State {
  error: Error | null;
}

/**
 * 顶层错误兜底：本地演示数据损坏（或渲染异常）时不白屏，
 * 给出「一键重置演示」入口；重置即清除损坏的 localStorage 并回到概览。
 */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // 仅记录到控制台，不上报、不执行任何外部调用
    console.error("[ErrorBoundary] 渲染异常：", error, info.componentStack);
  }

  reset = () => {
    try {
      localStorage.removeItem("asm-workbench-local-v1");
    } catch {
      /* ignore */
    }
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--bg)",
          padding: 24,
        }}
      >
        <div className="panel" style={{ maxWidth: 520, padding: "22px 24px" }}>
          <div className="notice danger" style={{ marginBottom: 12 }}>
            <Icon name="warn" size={15} />
            <div>
              <b>本地演示数据损坏或页面渲染异常</b>
              <div style={{ marginTop: 4, fontSize: 12.5, color: "var(--ink-3)" }}>
                已拦截错误，应用未崩溃为空白页。可一键重置演示（清除本地备注、状态与演示任务）。
              </div>
            </div>
          </div>
          <div
            className="mono"
            style={{
              fontSize: 11.5,
              color: "var(--red)",
              background: "var(--red-soft)",
              borderRadius: 8,
              padding: "8px 10px",
              wordBreak: "break-all",
              marginBottom: 14,
            }}
          >
            {String(this.state.error.message || this.state.error)}
          </div>
          <button className="btn primary" onClick={this.reset}>
            <Icon name="refresh" size={14} /> 重置演示数据并重新载入
          </button>
        </div>
      </div>
    );
  }
}

import React, { useState } from "react";
import { StoreProvider, useStore } from "./services/store";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { ContextBar } from "./components/ContextBar";
import { Overview } from "./views/Overview";
import { Assets } from "./views/Assets";
import { Tasks } from "./views/Tasks";
import { Review } from "./views/Review";
import { Graph } from "./views/Graph";
import { Sources } from "./views/Sources";
import { Reports } from "./views/Reports";
import { AssetDrawer } from "./components/AssetDrawer";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { assetKey } from "./data/dataset";
import { Workbench } from "./views/Workbench";
import { HistoryEvidence } from "./views/HistoryEvidence";

function Shell() {
  const { selection, assets, clearSelection, reduceMotion, navigate } = useStore();
  const [wizardOpen, setWizardOpen] = useState(false);

  // 尊重减少动态效果设置（本地开关叠加系统偏好）
  React.useEffect(() => {
    document.documentElement.style.setProperty("--speed", reduceMotion ? "0ms" : "");
  }, [reduceMotion]);

  const selectedAsset = selection.assetKey
    ? assets.find((a) => assetKey(a) === selection.assetKey)
    : undefined;
  // assets / review / graph 视图内部自行渲染抽屉，避免重复
  const drawerRenderedInline =
    selection.view === "assets" ||
    selection.view === "review" ||
    selection.view === "graph";

  if (selection.view === "pilot") return <HistoryEvidence />;

  return (
    <div className="app">
      <Sidebar />
      <div style={{ gridArea: "topbar" }}>
        <TopBar onNewTask={() => { navigate("tasks"); setWizardOpen(true); }} />
      </div>
      <div
        style={{
          gridArea: "main",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <ContextBar />
        <main className="main" style={{ flex: 1 }}>
          {selection.view === "overview" && <Overview />}
          {selection.view === "assets" && <Assets />}
          {selection.view === "tasks" && (
            <Tasks wizardOpen={wizardOpen} setWizardOpen={setWizardOpen} />
          )}
          {selection.view === "review" && <Review />}
          {selection.view === "graph" && <Graph />}
          {selection.view === "sources" && <Sources />}
          {selection.view === "reports" && <Reports />}
        </main>
      </div>
      {/* 概览 / 任务 / 来源 / 报告视图也允许打开资产抽屉 */}
      {!drawerRenderedInline && selectedAsset && (
        <AssetDrawer asset={selectedAsset} onClose={clearSelection} />
      )}
    </div>
  );
}

export default function App() {
  const query = new URLSearchParams(window.location.search);
  const [legacy, setLegacy] = useState(query.get("demo") === "1" || query.get("pilot") === "1");
  if (query.get("pilot") === "1") {
    return <ErrorBoundary><HistoryEvidence /></ErrorBoundary>;
  }
  if (!legacy) {
    return <ErrorBoundary><Workbench onDemo={() => setLegacy(true)} onReplay={() => {
      window.location.search = "?pilot=1";
    }} /></ErrorBoundary>;
  }
  return (
    <ErrorBoundary>
      {query.get("demo") !== "1" && <button className="btn" style={{position:"fixed",right:12,bottom:12,zIndex:1000}} onClick={() => { window.location.search = ""; }}>返回真实工作台</button>}
      <StoreProvider>
        <Shell />
      </StoreProvider>
    </ErrorBoundary>
  );
}

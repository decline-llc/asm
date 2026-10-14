import React from "react";
import { useStore } from "../services/store";
import type { SourceCapability } from "../types";
import { Badge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";

const CAP_LABEL: Record<SourceCapability, { label: string; tone: "ok" | "info" | "warn" | "neutral" | "danger" }> = {
  installed: { label: "工具已安装", tone: "info" },
  adapter: { label: "适配器存在", tone: "info" },
  integrated: { label: "主流程已接入", tone: "ok" },
  "offline-verified": { label: "离线已验证", tone: "ok" },
  "online-verified": { label: "实网已验证", tone: "ok" },
  "no-credential": { label: "未配置凭据", tone: "warn" },
};

export function Sources() {
  const { sources } = useStore();
  const engines = sources.filter((s) => s.category === "search-engine");
  const tools = sources.filter((s) => s.category === "tool");

  const renderCard = (s: (typeof sources)[number]) => (
    <div className="panel" key={s.id} style={{ padding: "14px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>{s.name}</h3>
        {s.inMainFlow && <Badge tone="ok">主流程</Badge>}
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "8px 0" }}>
        {s.capabilities.map((c) => (
          <Badge key={c} tone={CAP_LABEL[c].tone}>{CAP_LABEL[c].label}</Badge>
        ))}
      </div>
      <dl className="fields" style={{ fontSize: 12.3 }}>
        <dt>演示调用</dt>
        <dd className="num">{s.demoCalls === null ? "未运行" : `${s.demoCalls} 次`}</dd>
        <dt>配置额度</dt>
        <dd>{s.quota}</dd>
        <dt>结果数量</dt>
        <dd className="num">{s.resultCount === null ? "未运行" : s.resultCount}</dd>
        <dt>最近错误</dt>
        <dd style={{ color: s.lastError ? "var(--red)" : "var(--ink-3)" }}>
          {s.lastError ?? "无（与「未运行」区分展示）"}
        </dd>
      </dl>
      <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-3)" }}>{s.note}</div>
    </div>
  );

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>数据来源</h2>
        <span className="desc">
          能力分级展示，不用统一绿灯概括；密钥仅以掩码演示，浏览器不保存真实密钥
        </span>
      </div>

      <div className="notice warn">
        <Icon name="warn" size={14} />
        当前主流程自动查询以 FOFA / Quake 为主，另四家已有适配器但未全部接入主调度；
        DNS 可信解析路径存在已知待解决问题（见资产详情 DNS 页签的异常观测证据）。
      </div>

      <h3 style={{ margin: "14px 0 10px", fontSize: 14 }}>网络空间搜索引擎</h3>
      <div className="grid cols-3">{engines.map(renderCard)}</div>

      <h3 style={{ margin: "18px 0 10px", fontSize: 14 }}>采集工具（WSL 执行层）</h3>
      <div className="grid cols-3">{tools.map(renderCard)}</div>

      <div className="panel" style={{ marginTop: 14, padding: "14px 16px" }}>
        <h3 style={{ margin: "0 0 8px", fontSize: 13 }}>凭据配置（掩码演示）</h3>
        <dl className="fields" style={{ fontSize: 12.3 }}>
          <dt>FOFA_KEY</dt><dd className="mono">demo_••••••••3f9a（仅掩码演示值）</dd>
          <dt>QUAKE_KEY</dt><dd className="mono">demo_••••••••7b21（仅掩码演示值）</dd>
          <dt>HUNTER_KEY</dt><dd className="mono">未配置</dd>
          <dt>说明</dt>
          <dd>不收集真实密钥、不在浏览器保存真实密钥；后端通过 .env 注入，前端待接入配置接口。</dd>
        </dl>
      </div>
    </div>
  );
}

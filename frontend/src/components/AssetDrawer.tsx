import React, { useMemo, useState } from "react";
import { useStore } from "../services/store";
import { assetKey, isFakeIp } from "../data/dataset";
import type { Asset } from "../types";
import { Badge, ConfBadge } from "./Badge";
import { Icon } from "./Icons";
import { Screenshot } from "./Screenshot";
import { useFocusTrap } from "./useFocusTrap";

const TABS = ["概况", "证据", "DNS", "Web 与截图", "相关关系"] as const;

export function observationTool(asset: Pick<Asset, "kind" | "service" | "sources">): string {
  if (asset.kind === "web" || /^https?$/.test(asset.service)) return "httpx";
  if (asset.sources.some((source) => /nmap|端口扫描/i.test(source))) return "nmap";
  return "service_observation";
}

/** 资产详情抽屉：Esc 关闭、焦点圈定与恢复 */
export function AssetDrawer({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const { domains, companies, relations, graphNodes, navigate, openLead, leads } =
    useStore();
  const [tab, setTab] = useState<(typeof TABS)[number]>("概况");
  // 统一焦点管理：延迟一帧聚焦（修复 Enter 跳转闪退）、Tab 圈定、Esc、关闭恢复
  const drawerRef = useFocusTrap<HTMLElement>({ onClose });

  const domain = useMemo(
    () => domains.find((d) => d.domain === asset.host),
    [domains, asset.host]
  );
  const company = companies.find((c) => c.cid === asset.cid);
  const key = assetKey(asset);
  // 相关关系：优先按 refId === 资产主键匹配服务节点，再并入域名/IP 邻域
  // （不再用脆弱的 host.split 拼 id；无 refId 的资产回退到域名/地址邻域）
  const rels = useMemo(() => {
    const serviceNode = graphNodes.find((n) => n.type === "service" && n.refId === key);
    const domainNode = graphNodes.find(
      (n) => n.type === "domain" && (n.refId === asset.host || n.id === `d:${asset.host.split(".")[0]}`)
    );
    const ipNode = graphNodes.find((n) => n.type === "ip" && n.id === `ip:${asset.ip}`);
    const ids = new Set(
      [serviceNode?.id, domainNode?.id, ipNode?.id].filter(Boolean) as string[]
    );
    if (ids.size === 0) return relations.filter(() => false);
    return relations.filter((r) => ids.has(r.from) || ids.has(r.to));
  }, [graphNodes, relations, key, asset.host, asset.ip]);

  const relatedLeads = leads.filter((l) => l.relatedAssetKey === key);

  const copy = (text: string, label: string) => {
    const fallback = () => window.prompt(`复制${label}（手动选择复制）：`, text);
    if (!navigator.clipboard?.writeText) {
      fallback();
      return;
    }
    navigator.clipboard.writeText(text).then(
      () => window.alert(`已复制${label}（演示）：${text}`),
      () => fallback()
    );
  };

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside
        ref={drawerRef}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`资产详情 ${asset.host}:${asset.port}`}
        tabIndex={-1}
      >
        <div className="drawer-head">
          <div>
            <h3 className="mono">
              {asset.host}:{asset.port}/{asset.proto}
            </h3>
            <div className="sub">
              {asset.title || asset.service || "未识别服务"} · 最近观测{" "}
              <span className="mono">{asset.lastSeen.replace("T", " ").replace("Z", "")}</span>
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="关闭详情（Esc）">
            <Icon name="close" size={17} />
          </button>
        </div>
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="drawer-body">
          {tab === "概况" && (
            <>
              <dl className="fields">
                <dt>主键</dt>
                <dd className="mono">
                  {asset.host} + {asset.port} + {asset.proto}
                  <button className="btn ghost small" onClick={() => copy(`${asset.host}|${asset.port}|${asset.proto}`, "主键")}>
                    <Icon name="copy" size={12} /> 复制
                  </button>
                </dd>
                <dt>选用地址</dt>
                <dd className="mono">{asset.ip}</dd>
                {asset.alternateIps && asset.alternateIps.length > 0 && (
                  <>
                    <dt>其余解析地址</dt>
                    <dd>
                      <span className="mono">{asset.alternateIps.join("、")}</span>
                      <span style={{ color: "var(--ink-3)", fontSize: 12 }}>
                        {" "}（同一资产的 CDN 双 A 记录；主键仍唯一，不重复成行）
                      </span>
                    </dd>
                  </>
                )}
                <dt>归属企业</dt>
                <dd>{company ? `${company.name}（${company.brand}）` : "未确认归属"}</dd>
                <dt>服务 / 产品</dt>
                <dd>
                  {asset.service} {asset.product && `· ${asset.product} ${asset.version}`}
                </dd>
                <dt>技术栈</dt>
                <dd>{asset.tech.length ? asset.tech.join("、") : "未识别"}</dd>
                <dt>CDN</dt>
                <dd>{asset.cdn ? "是（CDN 节点，归属供应商网络）" : "否"}</dd>
                <dt>置信度</dt>
                <dd>
                  <ConfBadge c={asset.confidence} />{" "}
                  <span style={{ color: "var(--ink-3)", fontSize: 12 }}>
                    置信度不等于风险严重程度
                  </span>
                </dd>
                <dt>来源</dt>
                <dd>{asset.sources.join("、")}</dd>
                <dt>标签</dt>
                <dd>
                  {asset.labels.length
                    ? asset.labels.map((l) => (
                        <Badge key={l} tone={l === "测试环境" ? "warn" : "info"}>
                          {l}
                        </Badge>
                      ))
                    : "—"}
                </dd>
                {asset.url && (
                  <>
                    <dt>URL</dt>
                    <dd className="mono">{asset.url}</dd>
                  </>
                )}
                {asset.fingerprint && (
                  <>
                    <dt>服务指纹</dt>
                    <dd className="mono">{asset.fingerprint}</dd>
                  </>
                )}
              </dl>
              {relatedLeads.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h4 style={{ margin: "0 0 8px", fontSize: 13 }}>关联待核对线索（{relatedLeads.length}）</h4>
                  {relatedLeads.map((l) => (
                    <div className="notice warn" key={l.id}>
                      <Icon name="warn" size={14} />
                      <div>
                        {l.reason}
                        <button className="btn ghost small" onClick={() => openLead(l.id)}>
                          前往复核
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "证据" && (
            <>
              <h4 style={{ margin: "0 0 10px", fontSize: 13 }}>证据透镜：原始观测 / 选用结果 / 采纳理由</h4>
              <div className="lens">
                <div className="lens-col">
                  <h4><Icon name="eye" size={13} /> 原始观测</h4>
                  <ul>
                    {(domain?.dnsObservations ?? []).flatMap((o) =>
                      o.answers.map((a) => (
                        <li key={`${o.upstream}-${a}`} className="mono">
                          {o.upstream} → {a}
                        </li>
                      ))
                    )}
                    {!domain && <li>仅端口探测观测：{asset.ip}</li>}
                    {domain?.dnsObservations.some((o) => o.note) && (
                      <li style={{ color: "var(--amber)" }}>
                        含异常观测（见 DNS 页签）
                      </li>
                    )}
                  </ul>
                </div>
                <div className="lens-col selected-col">
                  <h4><Icon name="check" size={13} /> 选用结果</h4>
                  <ul>
                    <li className="mono">{asset.ip}</li>
                    <li>服务：{asset.service} {asset.product} {asset.version}</li>
                    {asset.title && <li>标题：{asset.title}</li>}
                  </ul>
                </div>
                <div className="lens-col">
                  <h4><Icon name="evidence" size={13} /> 采纳理由</h4>
                  <ul>
                    <li>{domain?.selectReason ?? "端口探测直接观测，未涉及解析取舍"}</li>
                    <li>置信度 {asset.confidence}：来源 {asset.sources.join("、")}</li>
                  </ul>
                </div>
              </div>

              <h4 style={{ margin: "18px 0 10px", fontSize: 13 }}>来源时间线</h4>
              <div className="timeline">
                <div className="tl-item">
                  <div className="ts">{domain?.firstSeen?.replace("T", " ").replace("Z", "") ?? "—"}</div>
                  首次发现：{asset.sources[0]}
                </div>
                {asset.sources.slice(1).map((s) => (
                  <div className="tl-item" key={s}>
                    <div className="ts">交叉确认</div>
                    {s} 命中同一资产（多来源去重，不重复计数）
                  </div>
                ))}
                <div className="tl-item">
                  <div className="ts">{asset.lastSeen.replace("T", " ").replace("Z", "")}</div>
                  最近观测：{asset.sources[asset.sources.length - 1] ?? "端口/引擎观测"}
                  {asset.kind === "service" ? " 端口/服务观测" : " 探测存活"}
                </div>
              </div>

              <h4 style={{ margin: "18px 0 10px", fontSize: 13 }}>原始记录（文本安全渲染）</h4>
              <div className="log-box">
{`[${observationTool(asset)}] ${asset.url ?? `${asset.host}:${asset.port}`} [${asset.service}] [${asset.title || "no-title"}] [${asset.tech.join(",") || "-"}]
[fingerprint] ${asset.fingerprint ?? "未提取"}
[asset_key] ${asset.host}|${asset.port}|${asset.proto}
[confidence] ${asset.confidence}  [sources] ${asset.sources.join(",")}`}
              </div>
            </>
          )}

          {tab === "DNS" && (
            <>
              {!domain && <div className="notice info">该资产为纯 IP 服务，无域名解析记录。</div>}
              {domain && (
                <>
                  <h4 style={{ margin: "0 0 10px", fontSize: 13 }}>多上游观测差异</h4>
                  <table className="data">
                    <thead>
                      <tr>
                        <th>上游</th>
                        <th>应答</th>
                        <th>观测时间</th>
                        <th>备注</th>
                      </tr>
                    </thead>
                    <tbody>
                      {domain.dnsObservations.map((o, i) => {
                        const isFake = o.answers.some((a) => isFakeIp(a));
                        return (
                          <tr key={i} style={{ cursor: "default", background: isFake ? "var(--red-soft)" : undefined }}>
                            <td className="mono">{o.upstream}</td>
                            <td className="mono">
                              {o.answers.length ? o.answers.join("，") : "（无应答 / NXDOMAIN）"}
                            </td>
                            <td className="mono">{o.ts.replace("T", " ").replace("Z", "")}</td>
                            <td>
                              {isFake && <Badge tone="danger">fake-IP 异常观测</Badge>}
                              {o.note && !isFake && <span style={{ color: "var(--ink-3)" }}>{o.note}</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>

                  <h4 style={{ margin: "18px 0 10px", fontSize: 13 }}>CNAME 链</h4>
                  {domain.cnameChain.length ? (
                    <div className="mono" style={{ fontSize: 12.5 }}>
                      {domain.cnameChain.map((c, i) => (
                        <div key={c} style={{ paddingLeft: i * 16 }}>
                          {i > 0 && "└─ "}{c}
                          {i === domain.cnameChain.length - 1 && domain.selectedIps.length === 0 && (
                            <Badge tone="warn"> 末端 NXDOMAIN（悬空候选）</Badge>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ color: "var(--ink-3)", fontSize: 12.5 }}>无 CNAME，直接 A/AAAA 记录。</div>
                  )}

                  <h4 style={{ margin: "18px 0 10px", fontSize: 13 }}>选用地址与理由</h4>
                  <dl className="fields">
                    <dt>选用地址</dt>
                    <dd className="mono">{domain.selectedIps.length ? domain.selectedIps.join("，") : "未选用（无有效应答）"}</dd>
                    <dt>选用理由</dt>
                    <dd>{domain.selectReason}</dd>
                  </dl>
                  <div className="notice warn" style={{ marginTop: 12 }}>
                    <Icon name="warn" size={14} />
                    DNS 可信解析路径存在已知待解决问题；异常观测仅作证据留存，不进入扫描队列。
                  </div>
                </>
              )}
            </>
          )}

          {tab === "Web 与截图" && (
            <>
              <dl className="fields" style={{ marginBottom: 14 }}>
                <dt>URL</dt>
                <dd className="mono">{asset.url ?? "（非 Web 服务）"}</dd>
                <dt>页面标题</dt>
                <dd>{asset.title || "未获取"}</dd>
                <dt>技术栈</dt>
                <dd>{asset.tech.join("、") || "未识别"}</dd>
              </dl>
              <Screenshot state={asset.screenshot} host={asset.host} port={asset.port} title={asset.title} />
              <div className="notice info" style={{ marginTop: 12 }}>
                <Icon name="camera" size={14} />
                演示截图为本地生成的页面缩略示意图，非真实采集图片。
              </div>
            </>
          )}

          {tab === "相关关系" && (
            <>
              {rels.length === 0 && (
                <div className="empty">
                  <div className="ico">⌀</div>
                  该资产暂无图谱关系记录。
                </div>
              )}
              {rels.map((r) => {
                const from = graphNodes.find((n) => n.id === r.from);
                const to = graphNodes.find((n) => n.id === r.to);
                return (
                  <div key={r.id} className="panel" style={{ marginBottom: 8, padding: "10px 12px" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <span className="mono">{from?.label ?? r.from}</span>
                      <Badge tone={r.status === "verified" ? "ok" : r.status === "candidate" ? "warn" : "danger"}>
                        {r.label}
                      </Badge>
                      <span className="mono">{to?.label ?? r.to}</span>
                    </div>
                    <div style={{ marginTop: 6, fontSize: 12, color: "var(--ink-3)" }}>
                      证据：{r.evidence}
                    </div>
                  </div>
                );
              })}
              <button className="btn" style={{ marginTop: 8 }} onClick={() => navigate("graph", { assetKey: `${asset.host}|${asset.port}|${asset.proto}` })}>
                <Icon name="graph" size={14} /> 在关系图谱中定位
              </button>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

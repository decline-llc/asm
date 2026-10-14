import React, { useEffect, useMemo, useState } from "react";
import { useStore } from "../services/store";
import { assetKey, isFakeIp, isTrustedAsset, isTrustedConfidence } from "../data/dataset";
import type { Asset } from "../types";
import { Badge, ConfBadge } from "../components/Badge";
import { Icon } from "../components/Icons";
import { Breadcrumb } from "../components/Breadcrumb";
import { AssetDrawer } from "../components/AssetDrawer";
import { downloadCsv, toCsv } from "../services/csv";

type TabKey = "domains" | "ips" | "services" | "web" | "quarantine";

const ALL_COLS = [
  { key: "asset", label: "资产", fixed: true },
  { key: "port", label: "端口/协议" },
  { key: "title", label: "标题" },
  { key: "company", label: "公司归属" },
  { key: "tech", label: "技术栈" },
  { key: "cdn", label: "CDN" },
  { key: "confidence", label: "置信度" },
  { key: "sources", label: "来源" },
  { key: "lastSeen", label: "最近观测" },
] as const;

const PAGE_SIZE = 10;

export function Assets() {
  const {
    assets, quarantine, domains, companies, selection, openAsset, clearSelection,
    assetFilter, setAssetFilter,
  } = useStore();

  // 筛选状态提升到 store：切换视图再返回时保留页签/筛选/排序/分页/勾选
  const tab = assetFilter.tab as TabKey;
  const q = assetFilter.q;
  const fCompany = assetFilter.fCompany;
  const fSource = assetFilter.fSource;
  const fConf = assetFilter.fConf;
  const fPort = assetFilter.fPort;
  const fCdn = assetFilter.fCdn;
  const fLabel = assetFilter.fLabel;
  const sortKey = assetFilter.sortKey;
  const sortAsc = assetFilter.sortAsc;
  const page = assetFilter.page;
  const checked = useMemo(() => new Set(assetFilter.checked), [assetFilter.checked]);

  const setTab = (t: TabKey) => setAssetFilter({ tab: t });
  const setQ = (v: string) => setAssetFilter({ q: v });
  const setFCompany = (v: string) => setAssetFilter({ fCompany: v });
  const setFSource = (v: string) => setAssetFilter({ fSource: v });
  const setFConf = (v: string) => setAssetFilter({ fConf: v });
  const setFPort = (v: string) => setAssetFilter({ fPort: v });
  const setFCdn = (v: string) => setAssetFilter({ fCdn: v });
  const setFLabel = (v: string) => setAssetFilter({ fLabel: v });
  const setSortKey = (v: string) => setAssetFilter({ sortKey: v });
  const setSortAsc = (v: boolean) => setAssetFilter({ sortAsc: v });
  const setPage = (v: number | ((p: number) => number)) =>
    setAssetFilter({ page: typeof v === "function" ? v(page) : v });
  const setChecked = (next: Set<string>) => setAssetFilter({ checked: [...next] });

  const [colsOpen, setColsOpen] = useState(false);
  const [visibleCols, setVisibleCols] = useState<Set<string>>(
    new Set(ALL_COLS.map((c) => c.key))
  );

  // 从其它视图跳转：域名定位
  useEffect(() => {
    if (selection.domain) {
      setTab("domains");
      setQ(selection.domain);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection.domain]);

  const companyName = (cid: string | null) =>
    cid ? companies.find((c) => c.cid === cid)?.brand ?? cid : "未确认";

  const allSources = useMemo(
    () => [...new Set(assets.flatMap((a) => a.sources))].sort(),
    [assets]
  );
  const allLabels = useMemo(
    () => [...new Set(assets.flatMap((a) => a.labels))].sort(),
    [assets]
  );
  const allPorts = useMemo(
    () => [...new Set(assets.map((a) => a.port))].sort((a, b) => a - b),
    [assets]
  );

  // ---- 资产行（服务/网页页签共用）----
  // 口径与后端 destination() 对齐：isTrustedAsset 判定；D/D+ 与未佐证 C 仅在隔离页签展示
  const filtered = useMemo(() => {
    let rows = assets.filter(isTrustedAsset);
    if (tab === "services") rows = rows.filter((a) => a.kind === "service" || a.kind === "web");
    if (tab === "web") rows = rows.filter((a) => a.kind === "web");
    if (fCompany === "__null") rows = rows.filter((a) => a.cid === null);
    else if (fCompany) rows = rows.filter((a) => a.cid === fCompany);
    if (fSource) rows = rows.filter((a) => a.sources.includes(fSource));
    if (fConf) rows = rows.filter((a) => a.confidence === fConf);
    if (fPort) rows = rows.filter((a) => a.port === Number(fPort));
    if (fCdn) rows = rows.filter((a) => String(a.cdn) === fCdn);
    if (fLabel) rows = rows.filter((a) => a.labels.includes(fLabel));
    const s = q.trim().toLowerCase();
    if (s) {
      rows = rows.filter(
        (a) =>
          a.host.toLowerCase().includes(s) ||
          a.ip.toLowerCase().includes(s) ||
          a.title.toLowerCase().includes(s) ||
          a.service.toLowerCase().includes(s)
      );
    }
    const val = (a: Asset): string | number => {
      switch (sortKey) {
        case "port": return a.port;
        case "title": return a.title;
        case "company": return companyName(a.cid);
        case "confidence": return a.confidence;
        case "lastSeen": return a.lastSeen;
        default: return a.host;
      }
    };
    rows = [...rows].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      const cmp = typeof va === "number" ? va - (vb as number) : String(va).localeCompare(String(vb));
      return sortAsc ? cmp : -cmp;
    });
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assets, tab, q, fCompany, fSource, fConf, fPort, fCdn, fLabel, sortKey, sortAsc]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  useEffect(() => setPage(0), [tab, q, fCompany, fSource, fConf, fPort, fCdn, fLabel]);

  const hasFilter = !!(q || fCompany || fSource || fConf || fPort || fCdn || fLabel);
  const clearFilters = () => {
    setQ(""); setFCompany(""); setFSource(""); setFConf(""); setFPort(""); setFCdn(""); setFLabel("");
  };

  const sortBy = (key: string) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const exportRows = (rows: Asset[], name: string) => {
    const csv = toCsv(
      ["序号", "资产", "端口", "协议", "标题", "技术栈", "CDN", "公司归属", "来源", "置信度", "最近观测"],
      rows.map((a, i) => [
        i + 1, a.host, a.port, a.proto, a.title, a.tech.join("; "),
        a.cdn ? "是" : "否", companyName(a.cid), a.sources.join("; "),
        a.confidence, a.lastSeen,
      ])
    );
    downloadCsv(name, csv);
  };

  const selectedAsset = selection.assetKey
    ? assets.find((a) => assetKey(a) === selection.assetKey)
    : undefined;

  const toggleCol = (k: string) => {
    const next = new Set(visibleCols);
    if (next.has(k)) {
      if (k === "asset") return; // 主列固定
      next.delete(k);
    } else next.add(k);
    setVisibleCols(next);
  };

  const th = (key: string, label: string) =>
    visibleCols.has(key as never) ? (
      <th className="sortable" onClick={() => sortBy(key)} aria-sort={sortKey === key ? (sortAsc ? "ascending" : "descending") : undefined}>
        {label} {sortKey === key && (sortAsc ? "▲" : "▼")}
      </th>
    ) : null;

  return (
    <div>
      <Breadcrumb />
      <div className="page-title">
        <h2>资产探索</h2>
        <span className="desc">
          主键 host+port+proto；同一 host 的不同端口独立成行；多来源命中不重复计数
        </span>
      </div>

      <div className="panel">
        <div className="tabs" role="tablist">
          {(
            [
              ["services", "服务资产", filtered.length],
              ["web", "Web 页面", assets.filter((a) => a.kind === "web" && isTrustedAsset(a)).length],
              ["domains", "域名", domains.length],
              ["ips", "IP", new Set(assets.filter(isTrustedAsset).map((a) => a.ip)).size],
              ["quarantine", "隔离候选", quarantine.length],
            ] as [TabKey, string, number][]
          ).map(([k, label, n]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
              {label} <span className="n">{n}</span>
            </button>
          ))}
        </div>

        {(tab === "services" || tab === "web") && (
          <>
            <div className="filter-bar">
              <input type="search" placeholder="搜索 host / IP / 标题…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="搜索资产" />
              <select value={fCompany} onChange={(e) => setFCompany(e.target.value)} aria-label="按公司筛选">
                <option value="">公司：全部</option>
                {companies.map((c) => (
                  <option key={c.cid} value={c.cid}>{c.brand}</option>
                ))}
                <option value="__null">未确认归属</option>
              </select>
              <select value={fSource} onChange={(e) => setFSource(e.target.value)} aria-label="按来源筛选">
                <option value="">来源：全部</option>
                {allSources.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <select value={fConf} onChange={(e) => setFConf(e.target.value)} aria-label="按置信度筛选">
                <option value="">置信度：全部</option>
                {["A", "B", "C", "E"].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select value={fPort} onChange={(e) => setFPort(e.target.value)} aria-label="按端口筛选">
                <option value="">端口：全部</option>
                {allPorts.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <select value={fCdn} onChange={(e) => setFCdn(e.target.value)} aria-label="按 CDN 筛选">
                <option value="">CDN：全部</option>
                <option value="true">仅 CDN</option>
                <option value="false">非 CDN</option>
              </select>
              <select value={fLabel} onChange={(e) => setFLabel(e.target.value)} aria-label="按标签筛选">
                <option value="">标签：全部</option>
                {allLabels.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
              {hasFilter && (
                <button className="btn small ghost" onClick={clearFilters}>
                  清空筛选
                </button>
              )}
              <button className="btn small" onClick={() => setColsOpen(!colsOpen)} aria-expanded={colsOpen}>
                <Icon name="filter" size={13} /> 列设置
              </button>
              {checked.size > 0 && (
                <button
                  className="btn small"
                  onClick={() => {
                    const rows = filtered.filter((a) => checked.has(assetKey(a)));
                    exportRows(rows, `asm-选中资产-${rows.length}条-演示数据导出.csv`);
                  }}
                >
                  <Icon name="download" size={13} /> 导出选中（{checked.size}）
                </button>
              )}
              <button className="btn small primary" onClick={() => exportRows(filtered, `asm-可信资产-${filtered.length}条-演示数据导出.csv`)}>
                <Icon name="download" size={13} /> 导出当前结果 CSV
              </button>
              <span className="count-note">
                {filtered.length} 条结果{hasFilter && "（已筛选）"}
              </span>
            </div>

            {colsOpen && (
              <div className="filter-bar" style={{ background: "#fafbfc" }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>显示列：</span>
                {ALL_COLS.map((c) => (
                  <label key={c.key} style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 12.5 }}>
                    <input
                      type="checkbox"
                      checked={visibleCols.has(c.key)}
                      disabled={"fixed" in c && c.fixed === true}
                      onChange={() => toggleCol(c.key)}
                    />
                    {c.label}
                  </label>
                ))}
              </div>
            )}

            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th style={{ width: 30 }}>
                      <input
                        type="checkbox"
                        aria-label="全选本页"
                        checked={pageRows.length > 0 && pageRows.every((a) => checked.has(assetKey(a)))}
                        onChange={(e) => {
                          const next = new Set(checked);
                          pageRows.forEach((a) => {
                            if (e.target.checked) next.add(assetKey(a));
                            else next.delete(assetKey(a));
                          });
                          setChecked(next);
                        }}
                      />
                    </th>
                    {th("asset", "资产")}
                    {th("port", "端口/协议")}
                    {th("title", "标题")}
                    {th("company", "公司归属")}
                    {th("tech", "技术栈")}
                    {th("cdn", "CDN")}
                    {th("confidence", "置信度")}
                    {th("sources", "来源")}
                    {th("lastSeen", "最近观测")}
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((a) => {
                    const k = assetKey(a);
                    return (
                      <tr
                        key={k}
                        className={selection.assetKey === k ? "selected" : ""}
                        onClick={() => openAsset(k)}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === "Enter" && openAsset(k)}
                      >
                        <td onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            aria-label={`选择 ${k}`}
                            checked={checked.has(k)}
                            onChange={(e) => {
                              const next = new Set(checked);
                              if (e.target.checked) next.add(k);
                              else next.delete(k);
                              setChecked(next);
                            }}
                          />
                        </td>
                        {visibleCols.has("asset") && (
                          <td className="mono">
                            {a.host}
                            <div style={{ color: "var(--ink-3)", fontSize: 11 }}>{a.ip}</div>
                          </td>
                        )}
                        {visibleCols.has("port") && (
                          <td className="mono num">
                            {a.port}/{a.proto}
                          </td>
                        )}
                        {visibleCols.has("title") && (
                          <td style={{ maxWidth: 240 }}>
                            <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.title}>
                              {a.title || <span style={{ color: "var(--ink-3)" }}>—</span>}
                            </div>
                            {a.labels.map((l) => (
                              <Badge key={l} tone={l === "测试环境" ? "warn" : l === "待核对" ? "danger" : "info"}>{l}</Badge>
                            ))}
                          </td>
                        )}
                        {visibleCols.has("company") && <td>{companyName(a.cid)}</td>}
                        {visibleCols.has("tech") && <td style={{ fontSize: 12 }}>{a.tech.join(" · ") || "—"}</td>}
                        {visibleCols.has("cdn") && <td>{a.cdn ? <Badge tone="info">CDN</Badge> : "—"}</td>}
                        {visibleCols.has("confidence") && (
                          <td><ConfBadge c={a.confidence} /></td>
                        )}
                        {visibleCols.has("sources") && <td style={{ fontSize: 12 }}>{a.sources.join("、")}</td>}
                        {visibleCols.has("lastSeen") && (
                          <td className="mono" style={{ fontSize: 11.5 }}>{a.lastSeen.replace("T", " ").replace("Z", "")}</td>
                        )}
                      </tr>
                    );
                  })}
                  {pageRows.length === 0 && (
                    <tr style={{ cursor: "default" }}>
                      <td colSpan={visibleCols.size + 1}>
                        <div className="empty">
                          <div className="ico">∅</div>
                          {hasFilter ? "无匹配结果：请调整筛选条件" : "暂无资产数据"}
                          {hasFilter && (
                            <div style={{ marginTop: 8 }}>
                              <button className="btn small" onClick={clearFilters}>清空筛选</button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="filter-bar" style={{ borderTop: "1px solid var(--border)", borderBottom: 0 }}>
              <button className="btn small" disabled={page === 0} onClick={() => setPage(page - 1)}>
                ← 上一页
              </button>
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
                第 {page + 1} / {pageCount} 页
              </span>
              <button className="btn small" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}>
                下一页 →
              </button>
            </div>
          </>
        )}

        {tab === "domains" && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>域名</th><th>五类标注</th><th>置信度</th><th>选用地址</th>
                  <th>来源</th><th>归属</th><th>最近观测</th><th>可信资产</th>
                </tr>
              </thead>
              <tbody>
                {domains
                  .filter((d) => !q || d.domain.toLowerCase().includes(q.trim().toLowerCase()))
                  .map((d) => {
                    // 域名行：按 host 匹配可信资产；点击 = 进入「该域名筛选后的资产列表」
                    // （不再拼 domain|443|tcp 魔法键，也不再直接打开 D+ 资产详情）
                    const domAssets = assets.filter((a) => a.host === d.domain && isTrustedAsset(a));
                    const openList = () => {
                      setTab("services");
                      setQ(d.domain);
                    };
                    const isQuarantined = !isTrustedConfidence(d.confidence, d.sources);
                    return (
                      <tr
                        key={d.domain}
                        onClick={domAssets.length ? openList : undefined}
                        style={{ cursor: domAssets.length ? "pointer" : "default" }}
                        title={domAssets.length ? "查看该域名下的可信资产列表" : "该域名暂无资产记录"}
                      >
                        <td className="mono">{d.domain}</td>
                        <td><Badge tone={d.tag5 === "公开" ? "ok" : d.tag5 === "内网" ? "warn" : "neutral"}>{d.tag5}</Badge></td>
                        <td><ConfBadge c={d.confidence} /></td>
                        <td className="mono" style={{ fontSize: 12 }}>
                          {d.selectedIps.join("，") || <span style={{ color: "var(--amber)" }}>未选用</span>}
                        </td>
                        <td style={{ fontSize: 12 }}>{d.sources.join("、")}</td>
                        <td>{companyName(d.cid)}</td>
                        <td className="mono" style={{ fontSize: 11.5 }}>{d.lastSeen.replace("T", " ").replace("Z", "")}</td>
                        <td style={{ fontSize: 12 }}>
                          {domAssets.length > 0
                            ? <span style={{ color: "var(--accent)" }}>{domAssets.length} 项 →</span>
                            : <span style={{ color: "var(--ink-3)" }}>{isQuarantined ? "D/D+ 或未佐证来源见隔离页签" : "无资产记录"}</span>}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
            <div style={{ padding: "10px 16px", fontSize: 12, color: "var(--ink-3)", borderTop: "1px solid var(--border)" }}>
              说明：「公开 / 有解析未验证 / 内网 / 独立IP段 / 云部署」为资产分类，不是风险评分；
              点击域名行进入该域名筛选后的资产列表，D/D+ 归属待核实域名仅在隔离页签 / 线索工作台查看。
            </div>
          </div>
        )}

        {tab === "ips" && <IpTable assets={assets} onOpen={openAsset} onOpenList={(ip) => { setTab("services"); setQ(ip); }} />}

        {tab === "quarantine" && (
          <div className="table-wrap">
            <div className="notice danger" style={{ margin: "12px 16px 0" }}>
              <Icon name="warn" size={14} />
              D 级模糊搜索命中属于隔离区（assets_quarantine），永不进入可信资产统计与总表；
              不存在「一键升级为可信资产」操作，重新判断归属需补充新证据并交由后端规则处理。
            </div>
            <table className="data" style={{ marginTop: 8 }}>
              <thead>
                <tr>
                  <th>对象</th><th>标题</th><th>置信度</th><th>来源</th>
                  <th>隔离原因</th><th>观测时间</th>
                </tr>
              </thead>
              <tbody>
                {quarantine.map((qItem) => (
                  <tr key={qItem.id} style={{ cursor: "default" }}>
                    <td className="mono">{qItem.host}{qItem.port ? `:${qItem.port}` : ""}</td>
                    <td>{qItem.title}</td>
                    <td><ConfBadge c={qItem.confidence} /></td>
                    <td>{qItem.source}</td>
                    <td style={{ maxWidth: 320 }}>{qItem.reason}</td>
                    <td className="mono" style={{ fontSize: 11.5 }}>{qItem.observedAt.replace("T", " ").replace("Z", "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedAsset && (
        <AssetDrawer asset={selectedAsset} onClose={clearSelection} />
      )}
    </div>
  );
}

function IpTable({
  assets,
  onOpen,
  onOpenList,
}: {
  assets: Asset[];
  onOpen: (k: string) => void;
  onOpenList: (ip: string) => void;
}) {
  // IP 页签与服务页签同口径：只统计可信资产；D/D+ 与 fake-IP 不作为可打开的资产行
  const groups = useMemo(() => {
    const m = new Map<string, Asset[]>();
    for (const a of assets) {
      if (!isTrustedAsset(a)) continue;
      const list = m.get(a.ip) ?? [];
      list.push(a);
      m.set(a.ip, list);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [assets]);

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr><th>IP 地址</th><th>类型</th><th>开放服务数</th><th>端口</th><th>备注</th></tr>
        </thead>
        <tbody>
          {groups.map(([ip, list]) => {
            const isFake = isFakeIp(ip);
            const isV6 = ip.includes(":");
            const isPrivate = ip.startsWith("10.");
            return (
              <tr
                key={ip}
                onClick={() => onOpenList(ip)}
                style={{ cursor: "pointer" }}
                title={`查看该 IP 下的 ${list.length} 项可信资产`}
              >
                <td className="mono">{ip}</td>
                <td>
                  {isFake ? <Badge tone="danger">fake-IP 异常观测</Badge>
                    : isV6 ? <Badge tone="info">IPv6</Badge>
                    : isPrivate ? <Badge tone="warn">私网</Badge>
                    : <Badge tone="neutral">演示保留段</Badge>}
                </td>
                <td className="num">{list.length}</td>
                <td className="mono" style={{ fontSize: 12 }}>
                  {list.map((a) => `${a.port}/${a.proto}`).join("，")}
                </td>
                <td style={{ fontSize: 12, color: "var(--ink-3)" }}>
                  {isFake ? "仅异常观测，不成为可扫描资产地址" : `解析到该 IP 不代表其所有服务均属目标公司`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ padding: "10px 16px", fontSize: 12, color: "var(--ink-3)", borderTop: "1px solid var(--border)" }}>
        说明：IP 页签仅统计可信资产（口径与服务页签一致）；D/D+ 归属待核实地址与 fake-IP
        异常观测不出现在本表，仅在隔离页签 / 线索工作台查看。点击行进入该 IP 筛选后的资产列表。
      </div>
    </div>
  );
}

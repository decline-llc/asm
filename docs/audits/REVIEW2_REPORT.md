# 前端第二轮独立评审报告（R1–R10 修复复核 + 增量探针）

- **评审对象**：`frontend/`（kimi K3 修复后的当前工作区状态，dist 构建于 2026-10-10 21:45，晚于最后源码改动 21:28）
- **评审方式**：代码级复核（全部 13 个改动文件通读）+ `scripts/fix_frontend_verify.py` 全量复跑 + 本轮新增独立探针 `scripts/review2_probes.py`（对比度实测 / 三档视口 / R6 初始态 / 快照差分披露 / 回归抽查）
- **证据留存**：`docs/audits/review-artifacts/review2/`（复跑 verify-results.json、probe-results.json）；kimi 原轮产物在 `docs/audits/review-artifacts/fix/`（11 张 PNG + export-assets.csv + verify-results.json，共 13 个文件）
- **环境声明**：本轮在沙箱内 `tsc -b` 通过；`vite build` 因沙箱禁止 esbuild 子进程管道（spawn EPERM）无法在受限模式完成，dist 与源码时间戳一致性已核对；Playwright 验证以一次经批准的完全权限本地运行完成（仅访问 127.0.0.1 本地静态页，无外部网络）。另注：`docs/`、`scripts/` 在受限 shell 中不可写（Windows 文件权限问题），文本产物经文件工具落盘。

---

## 一、结论总览

| 项 | 结果 |
| --- | --- |
| R1–R10 修复 | **全部维持，53/53 断言独立复跑通过，0 页面 JS 错误** |
| 防退步清单（隔离不可一键升级、总表表头契约、证据透镜三分栏、DNS 异常标注、演示边界声明、响应式骨架） | 全部原样保留，断言通过 |
| 数字口径（可信 15 / 本轮新增 2 / D+ 待核实 2） | **独立复算一致，确认无误**（见 §六） |
| 上轮遗留 V1（对比度） | **实测确认不达标**（新发现 N1，P2） |
| 上轮遗留 V2（1920 视口） | **实测通过**（无横向溢出、4 列栅格、抽屉 620px） |
| 新增问题 | N1–N8 共 8 项（1 项 P2、1 项 P2/P3、2 项 P3、4 项 P4），另 1 项交付说明与实测不符（N3 附带） |

**总体判断**：R1–R10 的修复质量高、可复现、无回归；本轮新发现集中在「上轮明确未验证的视觉量化项」与「演示数据语义自洽性」，均不阻断交付，但 N1（对比度）与 N2（390px 溢出）建议列入下一轮必修。

---

## 二、R1–R10 逐项复核

| # | 修复声明 | 代码证据 | 浏览器证据（本轮复跑） | 结论 |
| --- | --- | --- | --- | --- |
| R1 | cloud 第二 CDN 地址并入 `alternateIps`，主键唯一 | `dataset.ts` L417–428（`ip: .21` + `alternateIps: [.22]`，仅一条）；类型 `Asset.alternateIps?` | 搜索 cloud 恰 1 行；抽屉显「选用地址 .21 + 其余解析地址 .22」；服务页签 15；导出 CSV 15 行主键零重复；总表 cloud 1 行且截图列保留 demo-shot-cloud.png | ✅ |
| R2 | FOFA 去 online-verified；naabu/WSL httpx/gowitness 改「已安装，未接入」；子任务工具名同步 | `dataset.ts` L938–952：FOFA capabilities=[installed,adapter,integrated,offline-verified,no-credential]；三工具 inMainFlow=false + note 注明承担者；任务子任务 st3=nmap、st4=httpx (Windows)、st5=playwright-截图 | 主流程徽章恰 7（FOFA/Quake/OneForAll/dnsx/nmap/httpx-win/Playwright）；「实网已验证」零出现；「WSL 完整接入」仅存于 ffuf 待实现语境 | ✅ |
| R3 | 概览/报告共用 `diffNewAssetKeys()`，快照只存可信键，时间入窗口 | `dataset.ts` L888–928（快照 14→15 键，均合法可信键）；Overview/Reports 均 import 同一函数 | 两视图同显「新增可信资产 2（api:9090、lab:9200）」，无「约」字 | ✅（差分单向性问题见 N4） |
| R4 | Enter `preventDefault()` + 聚焦延迟一帧 | `SearchModal.tsx` L99–106（preventDefault）；`useFocusTrap.ts` L37–40（requestAnimationFrame 延迟聚焦） | Ctrl+K→↓→Enter 后抽屉保持打开、搜索框关闭、焦点在抽屉内 | ✅ |
| R5 | IP/域名页签同按 `isTrustedAsset()` 过滤；域名行进筛选列表；无资产域名不可点 | `Assets.tsx` L431–458（domAssets 判定 + openList）、L519–529（IpTable 同口径） | IP 页签无 192.0.2.200/198.51.100.50；点 shop 不开抽屉；点 iot 进入筛选列表有结果；无资产域名显示「无资产记录」 | ✅ |
| R6 | mkStages 失败判定前置；advanceTask 阶段↔子任务映射；allTasks 按 id 去重 | `store.tsx` L463–477（Map 去重 + STAGE_SUBTASK 映射）；`dataset.ts` L825–838 | 列表每 run 一卡；partial-failed 流程含 ✕；重试 +3；推进至 8/8 后 report 子任务完成无悬挂 | ✅（初始态 s8/st6 不一致见 N3） |
| R7 | loadLocal 逐字段校验归一；ErrorBoundary 一键重置 | `store.tsx` L51–216（normTask/normStages/normSubtasks/normLead* 全字段校验）；`ErrorBoundary.tsx`（getDerivedStateFromError + 重置按钮） | 注入 `demoTasks:[{id,name}]` 后 root 正常渲染（16809 字符）；非法 JSON 自愈；重置后恢复 15/14/12/2 | ✅ |
| R8 | isTrustedAsset 镜像 precision.py；192.0.2.10:8081 降 D | `dataset.ts` L961–975（A/B 可信；C 需 ≥2 来源；D/D+/E/F 隔离） | 可信 15；单来源 C（iot:5683）与无归属 502 均不入可信与总表 | ✅ |
| R9 | 筛选状态提升到 store（会话内存） | `store.tsx` L322–326 + `types/index.ts` AssetFilter（11 字段） | 设「澄川云+FOFA」→图谱→返回，筛选与「3 条结果」完整保留 | ✅ |
| R10 | 三弹层统一 useFocusTrap | `useFocusTrap.ts`（Tab 循环、Esc、关闭恢复 opener，捕获阶段监听） | 抽屉内 Tab/Shift+Tab 12 次不出容器；Esc 后焦点回 BUTTON；向导可 Esc | ✅ |

附带 6 项 P3 小修（#11–#16）抽查：#11 按钮名「导出当前结果 CSV」✅；#12 相关关系按 `refId === 资产主键` 匹配（AssetDrawer L28–39）✅；#13 证据时间线不再写死 httpx ✅（但「原始记录」框仍写死 `[httpx]` 前缀，见 N6）；#14 `isFakeIp()` 按 198.18.0.0/15 整数网段判断 ✅；#15 复制失败降级 `window.prompt` 手动选择 ✅；#16 `csvEscape` 先 lstrip 起始空白再判公式前缀、清理控制字符，与后端 s8 对齐 ✅。

**验证脚本方法学审计**：53 项断言均为真实 DOM/内容/下载检查（非字符串自证）；`R3.汇报视图` 断言的条件表达式写法略绕（`A and B if C else False`）但语义正确；`R6.推进后8/8完成` 用「已完成」子串判定略宽，建议下轮改为检查全部阶段节点均为 ✓。总体可信。

---

## 三、防退步清单复核

| 防退步项 | 证据 | 结论 |
| --- | --- | --- |
| 隔离不可一键升级 | Assets 隔离页签说明 + 无任何升级按钮（代码与页面均确认） | ✅ |
| 总表表头契约 | 前端 9 列与 `asm/stages/s8_report.py` L16 `序号/资产/端口/标题/技术栈/等级标注/来源/置信度/截图链接` **逐字一致** | ✅ |
| 证据透镜三分栏 | 断言「原始观测/选用结果/采纳理由」三栏存在 | ✅ |
| DNS 异常标注 | fake-IP 行红底 + danger 徽章 +「仅异常观测，不进入扫描队列」警示 | ✅ |
| 演示边界声明 | 任务详情、向导、截图页、报告页均有「演示/不执行真实扫描」声明；XLSX/HTML 下载禁用不空点 | ✅ |
| 响应式骨架 | 1280/1920 无溢出、栅格降列正常；**390px 存在 69px 横向溢出（N2，新发现）** | ⚠️ |

---

## 四、上轮遗留项实测（V1 / V2）

### V1 对比度（GLM 报告 §4 疑似值）——实测确认不达标（新发现 N1，建议 P2）

对 7 个视图全量采样（computed color × 祖先有效背景，WCAG 2.x 公式），**共 253 个文本元素实例低于 AA 4.5:1**（小字号）：

| 失败组合（前景 on 背景 @字号） | 实例数 | 实测对比度 | 需求 |
| --- | --- | --- | --- |
| `#6b7f8f`(--ink-3) on `#ffffff` @11.5–13px（hint/foot/desc/表单提示/调查路径 k 标签） | 119 | **4.15** | 4.5 |
| `#6b7f8f` on `#f4f6f8`(--bg) @12.5–13.5px（search-trigger、页面 desc） | 14+ | **3.83** | 4.5 |
| `#b7791f`(--amber) on `#fdf3e0` @11.5px（warn 徽章） | 37 | **3.31** | 4.5 |
| `#2f855a`(--green) on `#e8f5ee` @11.5px（conf-A 徽章 ●A） | 28 | **4.05** | 4.5 |
| `#5d7488`(--bluegray) on `#edf1f5` @11.5px（conf-C 徽章 ◐C） | 16 | **4.28** | 4.5 |

红色徽章 `#c0392b` on `#fdeceb` 实测约 **4.76:1，达标**（不在失败集）。GLM 上轮的估算（3.9 / 3.2）方向正确、数值精确到本实测。

**修复建议（改 `styles.css` 令牌后必须复测）**：`--ink-3` → `#5a6e7e`（白底 ≈5.30、bg 上 ≈4.89）；`--amber` → `#96601a`（amber-soft 上 ≈4.79）；`--green` → `#276749`（green-soft 上 ≈6.0）；`--bluegray` → `#4a6172`（bluegray-soft 上 ≈5.71）。以「样本明细前 25」为零回归基线（见 probe-results.json）。

### V2 1920 视口——实测通过

1920×1080：`scrollW=1920=clientW` 无横向溢出；cols-4 保持 4 列（stat-card 403px）；侧栏 220px / 主区 1700px；抽屉打开 620px。1280×800 同样无溢出。**留白密度观感仍需人工确认（本轮只做了 DOM/样式测量，与上轮同样的限制声明）。**

---

## 五、新发现问题（本轮增量）

| # | 级别 | 问题 | 证据 | 建议 |
| --- | --- | --- | --- | --- |
| N1 | **P2** | 对比度不达标（详见 §四 V1） | probe P1：253 实例、5 组令牌组合 | 改 4 个颜色令牌 + 复测脚本断言（新增「对比度回归」断言入 verify 脚本） |
| N2 | **P2/P3** | 390px 视口页面横向溢出 69px（scrollW 459 > 390；sidebar/main 均被内容撑到 459px） | probe P2 | 排查侧栏导航项 min-width / 不换行内容；目标 `scrollW ≤ clientW`；GLM 上轮测过表格内部滚动但未报页面级溢出，属存量问题首次曝光 |
| N3 | **P3** | R6 初始态：阶段 s8 显示 `● 报告生成`（running）而子任务 st6 为「等待」，且 s7 失败时报告阶段不应处于运行态；**README L78 与交付说明写「s8 pending」，与实测不符** | probe P3：steps=「…✕ Web 识别与截图（17）、● 报告生成」，subs=「report 等待」 | `mkStages` 在存在 failed 阶段时，后续阶段应为 pending 而非 running（或至少 stage/subtask 状态对齐）；修正 README 表述 |
| N4 | **P3** | 快照差分只报新增不报移除：`oa.example.com|443` 在 10-02 快照可信集内、10-09 不在，但任何视图均无「离开可信集/降级」表述（概览仅作为调查路径域名节点出现） | probe P4；`diffNewAssetKeys()` 仅返回 cur−prev | `diffNewAssetKeys` 增加 removedKeys；概览/报告补一行「离开可信集 N 项（原因：单来源 C 未佐证/SaaS 排除）」 |
| N5 | **P4** | `mkStages` 生成畸形时间戳：started 为四段式 `2026-10-09T10:10:00:00Z`（JS `new Date()` → Invalid Date），finished 秒位三位数 `:014:00Z`（Python fromisoformat 亦拒绝）；当前未渲染，属潜伏数据缺陷 | `dataset.ts` L835–836 展开；Python 验证 i≥2 全部 invalid | 改为 `${T}1${i}:00Z` / `${T}1${i}:${String((i*7)%60).padStart(2,'0')}Z` 或统一时间构造函数；补一条 Date.parse 断言 |
| N6 | **P4** | 抽屉「原始记录（文本安全渲染）」框 `[httpx]` 前缀写死：非 HTTP 资产（smtp/coap 等）也显示 httpx 日志行，与 #13 的修复口径不一致 | `AssetDrawer.tsx` L238 | 按 `asset.kind`/`service` 选择前缀（httpx / nmap / 引擎观测） |
| N7 | **P4** | Assets 表格空态行 `colSpan={12}` 写死，隐藏列后与实际列数不符 | `Assets.tsx` L385 | `colSpan={visibleCols.size + 1}` |
| N8 | **P4** | `isDPlus` 用 `{confidence} as Asset` 断言 hack 依赖 isTrustedAsset 只读 confidence/sources 的实现细节 | `Assets.tsx` L436 | 提取 `isTrustedConfidence(conf, sources)` 纯函数复用 |

**交付说明精确性备注**：①「13 张截图」实为 11 张 PNG + export-assets.csv + verify-results.json 共 13 个产物；②「s7 failed/s8 pending」见 N3；③ 其余声明（53/53、数字口径、修改文件清单）与实测一致。

---

## 六、数字口径独立复算（应托付人要求确认）

- **可信资产 15**：按 `isTrustedAsset()`（A/B 直入；C 需 ≥2 来源；D/D+/E/F 隔离）逐条清点 21 条资产记录，恰 15 条入可信（A×7、B×7、双来源 C×1=lab:443），与页签/总表/导出/快照四处一致。✅
- **本轮新增 2**：`diffNewAssetKeys` = 10-09 快照 15 键 − 10-02 快照 14 键 = `api:9090`、`lab:9200`。**lab:9200 为 B 级（httpx 观测），可信规则下本就应计入——它出现在「新增」是因为本轮首次观测到该服务（10-02 快照无此键），而非口径变化**；GLM 报告预期「16 或按新口径重算」在镜像 `destination()` 后即为 15。✅
- **另有 2 条 D+ 待核实**：L003（shop.example.org）、L010（198.51.100.50:7547），均为 pending 状态 D+ 线索。✅
- 附带发现：净变化实为 +1（新增 2、移除 1=oa:443），当前 UI 不呈现移除侧（N4）。

## 七、遗留项确认（按上轮决策留待下轮）

#17 待核对口径分叉、#18 合并项（图谱 r16/r8 语义、noteDraft 残留、面包屑跨视图、数据规模扩充）——确认未做、不阻断、留待下轮（本轮探针未覆盖 #17/#18 细项，建议下轮一并处理时补对应断言）。

## 八、下一轮修复优先级建议

1. **P2**：N1 对比度令牌（附带新增对比度回归断言）
2. **P2/P3**：N2 390px 溢出
3. **P3**：N3 R6 初始态 + README 口径修正；N4 快照移除披露
4. **P4**：N5 畸形时间戳（顺手修，防未来渲染时暴雷）；N6 [httpx] 前缀；N7 colSpan；N8 类型 hack
5. 环境治理：修复 `docs/`、`scripts/` 的受限 shell 写权限（Windows 文件权限），避免每轮验证都需要提权/绕行

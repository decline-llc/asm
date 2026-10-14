# ASM Workbench 前端审阅报告（GLM 5.3）

审阅对象：`frontend/`（React 18 + TS + Vite 单页应用，作者交付说明为 `frontend/README.md`）。
审阅依据：`docs/audits/KIMI_K3_FRONTEND_PROMPT.md`（原始设计要求）、`asm/models.py`、`asm/precision.py`、`asm/stages/s8_report.py`、`README.md`、`HANDOFF.md`、`docs/COVERAGE.md`、`docs/OPERATIONS.md`、v2.0 设计文档第 4.2/4.3/4.5 节。
验证方式：全量源码审读 + `tsc -b` 类型检查通过 + 本地静态服务 dist 构建 + Playwright（Chromium 无头）执行设计提示词要求的链路 A/B 与 20 余项定向复现。截图与运行记录存于 `docs/audits/review-artifacts/`（本审阅环境不能直接读取图像内容，视觉结论均以 DOM/样式测量为证据，图像留待人工或视觉模型复核）。

---

## 1. 总体判断

**修复后可演示。**

关键依据：

- 两条核心演示链路可以走通：链路 A（概览 → L001 → 证据工作台 → 资产抽屉证据/DNS 页签 → 组合筛选 → CSV 导出）与链路 B（新建演示任务 → 重试失败子任务 → 计数更新 → 刷新持久化 → 重置）经浏览器实际执行成立；D 级隔离候选确实未进入可信指标与报告总表（运行确认）。
- 构建与类型检查通过（作者侧 `npm run build` 产物 17:20 晚于源码 16:33；本次 `tsc -b` exit 0。`vite build` 在审阅沙箱因 esbuild 子进程命名管道限制无法执行，非项目问题）。
- 但存在一个 P1（数据来源页对 FOFA「实网已验证」、WSL httpx/gowitness/naabu「主流程已接入」的能力误述，与 OPERATIONS.md/COVERAGE.md 事实相反）和一组 P2（可信口径与 UI 各处不一致、同主键重复资产破坏去重/导出、任务状态三处互相矛盾、键盘 Enter 搜索跳转抽屉闪退、畸形 localStorage 全应用白屏等）。这些问题集中、可修，不影响整体架构方向。
- 验证范围：链路 A/B 全程、7 个视图、390/1024/1440 视口的 DOM 级检查、CSV 内容比对、localStorage 持久化与容错。**未验证**：真实视觉观感（无图像输入能力）、1920 视口、打印输出效果、颜色对比度实测、触屏手势。

---

## 2. 需求核对表

结论取值：已验证符合 / 确认不符合 / 待验证 / 不适用。

| # | 设计要求 | 实现位置 | 验证方式 | 结论 |
|---|---|---|---|---|
| 1 | 独立 `frontend/`，不改 Python/CLI/SQLite/报告/原 HTML | `frontend/` 目录整体 | glob 对比仓库根 | 已验证符合 |
| 2 | React+TS+Vite，页面/组件/类型/数据/服务分层 | `src/` 各目录 | 代码审读 | 已验证符合 |
| 3 | 读写经可替换数据服务，组件不直接绑演示数组 | `services/store.tsx` 统一出口 | 代码审读（仅 store 导入 dataset） | 已验证符合 |
| 4 | 墨蓝侧栏+雾白+青绿，紧凑密度、等宽字体、8–12px 圆角 | `styles.css`（#12202e/#F4F6F8/#167D8D 等） | CSS 审读 | 已验证符合 |
| 5 | 顶部项目切换/搜索/最近运行/演示状态/新建入口 | `TopBar.tsx` | 运行检查 | **确认不符合（轻）**：无项目切换控件（单演示项目，向导中有「切换项目待后端支持」说明） |
| 6 | 上下文条：项目/run_id/模式/范围，可展开排除项 | `ContextBar.tsx` | 运行检查 | 已验证符合 |
| 7 | Ctrl+K 搜索匹配企业/域名/IP/服务标题/任务，键盘选择跳转 | `SearchModal.tsx` | 运行检查 | **确认不符合**：键盘 Enter 跳转后抽屉闪退（问题 #4），鼠标点击可用 |
| 8 | 四项主指标统一口径并写明统计口径 | `Overview.tsx` | 运行检查 | 部分符合：「本轮新增资产」含 2 个 D+ 隔离级资产且与报告中心口径（约 8）不一致（问题 #2/#3） |
| 9 | 可信资产 host+port+proto 去重，多来源不重复计数 | `dataset.ts trustedAssets`、`Assets.tsx` | 运行检查 | **确认不符合**：表格 20 行 vs 指标 19（同主键两行，问题 #1）；导出 CSV 含重复主键（运行确认） |
| 10 | D/D+ 不入可信统计与总表 | `Assets.tsx` 过滤、`Reports.tsx` master=trusted | 运行检查（master 19 行、无 shop/198.51.100.50） | 主表已验证符合；但 IP 页签与域名页签可打开 D+ 资产详情（问题 #5，边界仅在表格层过滤） |
| 11 | 隔离候选页签 + 不可一键升级 | `Assets.tsx` quarantine tab + 提示 | 运行检查 | 已验证符合（提示文案准确） |
| 12 | 置信度 A–F 与严重程度分离 | `Badge.tsx` ConfBadge/SeverityBadge、Review 工作台 | 运行检查 | 已验证符合（title 注明「与风险严重程度无关」） |
| 13 | 域名五类标注为资产分类不冒充风险 | `types DomainTag`、域名表 | 代码审读 | 已验证符合 |
| 14 | 证据透镜：原始观测/选用结果/选择理由 | `AssetDrawer.tsx` 证据页签 | 运行检查（lab 资产三栏内容） | 已验证符合 |
| 15 | DNS 多上游差异、CNAME 链、fake-IP 仅异常观测 | `AssetDrawer.tsx` DNS 页签 | 运行检查（198.18.0.23 标记） | 已验证符合（检测函数有 P3 瑕疵，见问题 #15） |
| 16 | 截图区分未采集/缺失/失败 + 演示标注 | `Screenshot.tsx` 四态 | 运行检查 | 已验证符合 |
| 17 | 四步向导：种子→范围确认→模式阶段→摘要 | `Tasks.tsx` TaskWizard | 运行检查 | 已验证符合（向导不支持 Esc 关闭，见问题 #16） |
| 18 | 股权≠授权范围声明（多处） | 向导/图谱/上下文条 | 运行检查 | 已验证符合 |
| 19 | 暂停/终止禁用并说明原因 | `Tasks.tsx` | 运行检查（按钮禁用+title） | 已验证符合 |
| 20 | 进度按计数，不伪造 ETA | TaskCard「正在处理，总量未知时不预估剩余时间」 | 运行检查 | 已验证符合 |
| 21 | P1/P2 顺序轨道不冒充并发 | `tracks` + 顺序声明 | 运行检查 | 已验证符合 |
| 22 | 复核工作台：备注/状态/操作历史本地持久化 | `Review.tsx` + store | 运行检查（刷新后备注在） | 已验证符合 |
| 23 | 502/泄露/悬空 CNAME 仅待核对线索 | L006/L009/L004 文案 | 运行检查 | 已验证符合 |
| 24 | 图谱：类型/关系筛选、点节点、双击开抽屉、定位选中 | `Graph.tsx` | 运行检查（26 节点 24 边，双击开抽屉成功） | 已验证符合（键盘不可操作图谱，见待验证 V3） |
| 25 | 来源页区分六级能力，不用统一绿灯 | `Sources.tsx` | 运行检查 | **确认不符合**：FOFA 标「实网已验证」、httpx 标「主流程已接入·WSL 完整接入」、gowitness/naabu 标「主流程已接入」——与项目事实相反（问题 #6，P1） |
| 26 | 额度未知显示「未提供」，未运行≠失败≠ 0 | Sources 卡片 | 运行检查 | 已验证符合 |
| 27 | 不收集/不保存真实密钥，掩码演示 | Sources 凭据区 | 运行检查 | 已验证符合 |
| 28 | 八表映射 + 总表字段契约 | `Reports.tsx` | 运行检查（总表 19 行、表头完全一致、D+ 不入） | 已验证符合（master 截图列为演示文件名） |
| 29 | XLSX/HTML 未接后端时明确待接入或标注演示导出 | Reports 禁用按钮/导出命名 | 运行检查 | 已验证符合 |
| 30 | CSV 引号/换行/中文/公式前缀 | `services/csv.ts` | 代码审读 + 导出内容比对 | 基本符合；前缀检查未 lstrip 空白（与后端 `text_cell` 不一致，P3，问题 #17） |
| 31 | 演示数据规模建议 4–6 企/30–50 域/20–30 服务/8–12 任务/10–15 线索 | `dataset.ts` | 计数 | 部分符合：域名 14（<30）、任务 2（<8）为「建议」偏离，见改进建议 |
| 32 | localStorage 保存任务/备注 + 重置入口 | store + Review「重置演示」 | 运行检查（重置后恢复 19/14/12/7） | 已验证符合；但畸形数据会白屏（问题 #7） |
| 33 | 不执行真实扫描/第三方 API/shell，不冒充连接 WSL | 全局声明 + Sidebar「WSL 执行层：浏览器不可达」 | 代码审读 + 运行检查 | 已验证符合 |
| 34 | 键盘操作、可见焦点、抽屉 Esc | `:focus-visible`、AssetDrawer Esc | 运行检查 | 部分符合：Esc 可关、焦点可进入；无焦点圈定（trap）、关闭后焦点不恢复（BODY）、向导无 Esc（问题 #16） |
| 35 | 390/1024/1440 适配，窄屏抽屉全屏、表格横滚 | `styles.css` 断点 | DOM 测量（390 下 drawer 宽 390px、table-wrap 889>429 横滚、侧栏转为底部 79px 条） | 已验证符合 |
| 36 | 尊重减少动态效果 | `prefers-reduced-motion` + 本地开关 | CSS/代码审读 | 已验证符合 |
| 37 | 日志/外部文本安全渲染 | React 文本节点（无 dangerouslySetInnerHTML） | 代码审读 | 已验证符合 |

---

## 3. 已确认问题（按影响排序）

标注格式：**[影响级别｜证据类型]**。

### 问题 #1 [P1｜代码确认+运行复现] 同主键两条资产破坏「host+port+proto 去重」契约，表格/抽屉/导出三处数据互相矛盾

- **位置**：`frontend/src/data/dataset.ts` L416–434（`cloud.example.com|443|tcp` 两条：198.51.100.21「CDN 节点」与 198.51.100.22「CDN 节点 2」）；`frontend/src/views/Assets.tsx` 表格与导出；`frontend/src/App.tsx` L25–27 `assets.find` 首条命中。
- **触发条件**：演示数据集固定存在，任意视口。
- **复现步骤**：① 资产探索搜索 `cloud.example.com` → 服务资产表显示 2 行（表头声明「主键 host+port+proto；多来源命中不重复计数」，同表即自相矛盾）；② 统计口径：概览「可信资产 19」= Map 去重后，资产页签却显示「服务资产 20」= 原始行数；③ 点击第二行（表格显示 198.51.100.22）→ 抽屉「选用地址」显示 **198.51.100.21**；④ 「导出当前结果 CSV」→ 文件含两行同主键（`cloud.example.com,443,tcp` ×2）；⑤ 报告中心总表 19 行（去重后恰保留 .22 那条，其截图状态为「未采集」，丢失 .21 的已采集截图）。
- **预期**：一个 `host|port|proto` 只对应一条可信资产记录（后端 `assets UNIQUE(host,port,proto)`，v2.0 设计 4.2）；多地址应作为同一资产的字段（如选用地址列表）或多来源记录，不应成为两行资产。
- **影响**：核心口径「去重、不重复计数」在同一页面被表格、指标、抽屉、CSV 四处以三种数字呈现（20/19/两条）；导出的可信结果 CSV 违反主键唯一；总表去重时以「后写覆盖」任意丢弃 .21 的截图证据。
- **最小修复**：将第二 CDN 节点建模为同一资产的补充信息（例如 `Asset.alternateIps` 或证据条目），或在数据集中删除该重复行并把 198.51.100.22 记为 DNS 观测/证据；同时让表格行、页签计数、导出、总表统一从 `trustedAssets()` 派生。
- **验收**：搜索 cloud → 恰 1 行；页签计数 = 概览可信资产数；导出 CSV 主键无重复；总表该行截图状态与保留记录一致。

### 问题 #2 [P1｜代码确认+运行复现] 数据来源页把未接入/未验证的能力标为「主流程已接入 / 实网已验证」，与项目事实相反

- **位置**：`frontend/src/data/dataset.ts` L929–939：FOFA `capabilities:["…","online-verified"]`；naabu `integrated`+`inMainFlow`+「被动梳理模式回放」；httpx `integrated`+`inMainFlow`+note「WSL 完整接入」；gowitness `integrated`+`inMainFlow`。
- **事实依据**（仓库内文档）：`docs/OPERATIONS.md` L44–47「ProjectDiscovery httpx 已安装，未接入 Stage 7」「ffuf/katana 已安装，未接入 Stage 7」「gowitness 已安装，尚待每个浏览器请求的范围控制；当前截图由 Windows Playwright 承担」；L43「naabu 已安装，未接入阶段自动调度」；`HANDOFF.md` L15「所有凭据为空」；`docs/COVERAGE.md` L17「真实各家账户校验」尚需补齐。设计提示词 §6 亦明文要求「WSL 的 httpx/gowitness/ffuf/katana 完整接入仍待实现」。
- **复现步骤**：打开「数据来源」→ FOFA 卡显示绿色「实网已验证」徽章与「主流程」徽章；工具区 httpx/gowitness/naabu 三卡均显示「主流程已接入」绿色徽章（运行截图 `08-sources.png`）。任务详情的子任务表同样以 naabu/httpx/gowitness 作为执行工具（`11-task-run0109.png`），而真实后端端口扫描是 nmap、Web 探测是 Windows Python httpx、截图是 Windows Playwright。
- **影响**：审阅提示词明确「不能根据界面绿灯认定后台能力存在」。来源页是使用者判断平台能力的页面，四处绿灯虚构了不存在的接入与验证状态，属关键能力误述；即使在「演示数据」徽章下，也与同页警示条（FOFA/Quake 为主、四家适配器未接入）自相矛盾。
- **最小修复**：仅改 `dataset.ts`：FOFA 去掉 `online-verified`（凭据为空，保留 installed/adapter/integrated/offline-verified）；naabu、httpx、gowitness 去掉 `integrated` 与 `inMainFlow`，note 改为「已安装，未接入主流程；端口扫描由 nmap 承担 / Web 探测由 Windows httpx 承担 / 截图由 Windows Playwright 承担」；任务子任务工具名同步改为 nmap / httpx(Windows) / playwright-截图（或标注「演示工具名」）。
- **验收**：来源页无任何与 OPERATIONS.md 冲突的能力徽章；任务子任务工具与后端 Stage 6/7 实际引擎一致。

### 问题 #3 [P2｜代码确认+运行复现] 「本轮新增资产」指标混入 D+ 隔离级资产，且与报告中心「新增约 8 个」两种口径并存

- **位置**：`frontend/src/views/Overview.tsx` L17–21（`newAssets` = 快照 assetKeys 差集，含 `198.51.100.50|7547|tcp`、`shop.example.org|443|tcp` 两个 D+ 键）；`frontend/src/views/Reports.tsx` 汇报视图「较上轮变化 新增资产约 8 个」（原始长度 22−14，把 `#2` 伪键也计入）。
- **复现步骤**：概览显示「本轮新增资产 7」——其中 2 个为 D+ 隔离级（不计入「可信资产 19」）；报告中心汇报视图显示「新增资产约 8 个」。同屏对照：7 ≠ 8，且都不是「新增可信资产」。
- **影响**：四个主指标中两个（可信资产 vs 本轮新增）口径不一致；快照 `assetKeys` 使用 `#2` 后缀 hack（问题 #1 的连带），差分逻辑被迫写 `replace(/#\d+$/,"")` 补丁；「历史曲线、首次发现和本轮新增有对应快照依据」无法成立（10-09 有 9 条线索时间戳，快照却记 `newLeads: 7`；资产 lastSeen 14:35+ 而本轮运行 finishedAt 10:26，观测时间晚于运行结束 4 小时）。
- **最小修复**：快照 assetKeys 只存合法主键且区分口径（如 `trustedKeys` 与 `quarantineKeys`）；概览「本轮新增资产」改为「本轮新增可信资产 N（另有 X 条 D+ 待核实）」；报告中心复用同一差分函数，禁用「约」字凑数；对齐线索/资产时间戳与 run 的 finishedAt。
- **验收**：概览与报告中心的新增数字一致且可点击追溯到具体资产行；两条 D+ 资产不被计为新增可信资产。

### 问题 #4 [P2｜运行复现] 全局搜索键盘 Enter 跳转：抽屉渲染后被 Enter keyup 立即关闭，表现为「跳转无效」

- **位置**：`frontend/src/components/SearchModal.tsx` L96–99（Enter 分支）+ `frontend/src/components/AssetDrawer.tsx` L17–24（挂载即 `closeRef.current?.focus()`）。
- **触发条件**：任意视图按 Ctrl+K → 输入关键词 → ↑↓ 选择 → Enter。
- **复现步骤与证据**：MutationObserver 记录（`review_frontend_probe2.py`）：1631.8ms `ASIDE.drawer` 加入 DOM（openAsset 已生效、面包屑已更新）→ 抽屉 effect 把焦点移到关闭按钮 → 1632ms `BUTTON.drawer-close` 收到坐标 (0,0) 的合成 click（Enter keyup 落在刚获得焦点的按钮上）→ 1634.3ms 抽屉被 `clearSelection` 卸载。四个视图（overview/tasks/sources/assets）均复现；鼠标点击搜索结果则正常。
- **影响**：设计要求「支持 Ctrl/Cmd+K、键盘选择和跳转到对应详情」；键盘路径实际表现为跳转失败（抽屉闪现 2.5ms 即消失），键盘用户无法使用搜索跳转。
- **最小修复**：SearchModal Enter 分支调用 `e.preventDefault()`；并将 AssetDrawer 的初始聚焦改为「延迟一帧/微任务」或聚焦非激活元素（如 `tabIndex={-1}` 的容器），避免同一次按键的 keyup 落在关闭按钮上。两者取其一即可，建议都做。
- **验收**：Ctrl+K → ↓ → Enter 后抽屉保持打开且焦点在抽屉内；Esc 关闭后焦点返回搜索触发按钮。

### 问题 #5 [P2｜代码确认+运行复现] IP 页签与域名页签绕过隔离边界：D+ 待核实资产作为常规资产行展示并可打开详情

- **位置**：`frontend/src/views/Assets.tsx`（IP 页签直接遍历未过滤的 `assets`，含 shop 192.0.2.200 与 198.51.100.50；域名页签行点击 `openAsset(d.domain+"|443|tcp")`）。
- **复现步骤**：① IP 页签出现 `192.0.2.200`、`198.51.100.50` 行（服务/Web 页签则不含）→ 点击 `192.0.2.200` 行 → 打开 `shop.example.org:443/tcp` 抽屉（D+ 徽章）；② 域名页签点击 `shop.example.org` → 同样打开 D+ 资产抽屉；③ 域名页签点击 `iot.example.com`（无 443 资产）→ 无任何反应（设计要求「每个可点击控件要有可验证结果」）。
- **影响**：「D 级永不混入可信资产指标和总表」在服务/Web 页签成立，但 IP 页签的「开放服务数」把 D+ 资产计入，且两个页签都能把隔离级资产以常规详情呈现，边界口径不一致（审阅提示词第 2、7 条）。
- **最小修复**：IP 页签与域名页签行同样从 `TRUSTED_CONFIDENCE` 过滤后的资产生成；IP/域名行改为跳转到筛选后的资产列表（或域名下资产菜单），避免 `domain|443|tcp` 魔法键；无资产域名行改为不可点击并显示「无资产记录」。
- **验收**：IP 页签不出现 192.0.2.200/198.51.100.50；点击任何域名行都有可见结果；D+ 资产仅能从隔离页签/线索工作台进入。

### 问题 #6 [P2｜代码确认+运行复现] 任务状态三处互相矛盾：partial-failed 全绿、8/8 完成但子任务悬挂、同 ID 任务卡片重复

- **位置**：`frontend/src/data/dataset.ts` L833（`mkStages` 的 `failedAt` 分支因 `i < upto` 先命中而永远不生效，L848 `mkStages(7,6)` 实际产出 s1–s7 全 done + s8 running）；`frontend/src/services/store.tsx` L270–273（`allTasks = [...demoTasks, ...seedTasks]` 不按 id 去重）、L275–304（`advanceTask` 只翻转 running 子任务，pending/failed 子任务不跟进）。
- **复现步骤**：① 打开 RUN-20261009-01：状态徽章「部分失败」，阶段流程 7 项全绿 + 报告进行中，而同屏子任务表 gowitness「失败」、report「等待」——部分失败任务无任何失败标示；② 点「模拟推进一阶段」→ 卡片变「已完成 8/8」，但子任务表 report 仍「等待」；③ 返回列表 → 出现两张 `RUN-20261009-01` 卡片（一张 8/8 已完成、一张 7/8 部分失败），且重复副本随 localStorage 持久化。
- **影响**：调查任务是四个深视图之一，链路 B（模拟部分失败→重试→计数同步）的展示核心；同一任务的状态在徽章、阶段、子任务、列表四处出现四种说法，破坏演示可信度。
- **最小修复**：修正 `mkStages` 条件顺序（`failed` 判定置于 `i < upto` 之前，或改用显式状态表）并把种子任务的 s7 置为 failed、s8 pending；`advanceTask` 推进阶段时同步推进对应子任务（failed→done 记重试、pending→running），全部完成后归位 report 子任务；`allTasks` 合并时按 `id` 去重（demoTasks 覆盖 seedTasks）。
- **验收**：partial-failed 任务阶段流程出现 1 项失败标示；推进到 8/8 时无悬挂子任务；列表中每个 run_id 只有一张卡片；重试后 gowitness 结果数 +3（现状已符合）。

### 问题 #7 [P2｜运行复现] 畸形/旧版本 localStorage 数据导致整页白屏且无法通过界面恢复

- **位置**：`frontend/src/services/store.tsx` L43–51（`loadLocal` 只防「非法 JSON」，`{...defaultLocal(), ...JSON.parse(raw)}` 直接透传结构不明的对象）+ 视图层对 `t.stages` 等字段无防御（如 Overview `t.stages.filter`）。
- **复现步骤**：`localStorage['asm-workbench-local-v1'] = '{"demoTasks":[{"id":"X","name":"x"}],…}'` → 刷新 → 控制台 `TypeError: Cannot read properties of undefined (reading 'filter')`，`#root` 空白；再次刷新仍白屏（坏数据持久），UI 的「重置演示」不可达，只能手动清 localStorage。
- **影响**：审阅要求「本地存储需要合理处理无效 JSON、旧版本数据与重置」；无效 JSON 已处理，但字段缺失/旧版本形状未处理，且故障态不可自愈。演示工具的 v1 键名无版本迁移，未来任何字段演进都会触发同类崩溃。
- **最小修复**：`loadLocal` 对合并结果做字段级校验/归一（`demoTasks` 逐项校验必需字段，非法项丢弃；`leadStatus` 等做白名单过滤），校验失败回退 `defaultLocal()` 并清掉坏键；顶层加一个 ErrorBoundary 兜底渲染「数据损坏 → 一键重置演示」。
- **验收**：注入上例坏数据后应用可渲染且给出重置入口；重置后恢复 19/14/12/7。

### 问题 #8 [P2｜代码确认] 可信口径 `TRUSTED_CONFIDENCE = {A,B,C,E}` 与后端 precision.py 语义不一致，且注释声称「与后端语义对齐」

- **位置**：`frontend/src/data/dataset.ts` L943–945；后端 `asm/precision.py` L25–38：A/B→assets；C 需 ≥2 独立来源或三重归属才升入（升为 A）；D+ 仅中小企业例外入 assets；**其余（含 E、F）一律 `assets_quarantine`**。
- **触发条件**：静态规则，当前演示数据无 E/F 资产、C 级资产未建模佐证条件，故暂未造成数字差异；但 C 级单来源资产（iot:5683 仅 Quake、vpn:4433 仅端口扫描、oa:443 仅 Hunter）与无归属 502 资产（192.0.2.10:8081，cid=null、线索明言「归属未知」）均按可信计入 19。
- **影响**：演示的「可信资产」口径宽于后端红线（quarantine 永不进可信统计）；一旦接入真实数据或演示加入 E/F，前端会把后端会隔离的资产计入可信。注释「与后端语义对齐」不实。
- **最小修复**：口径函数改为镜像 `destination()`：A/B 可信；C 仅当 `sources.length>=2`（或显式 `corroborated` 标记）可信，否则归隔离展示；E/F 一律隔离；192.0.2.10:8081 降为 D 级待归属（或从可信统计剔除并单独说明）；同步修正注释与 Overview 的口径脚注。
- **验收**：单来源 C 与无归属资产不再计入「可信资产」；口径脚注与 precision.py 一一对应；演示数字同步更新（预期可信资产 16 或按新口径重算）。

### 问题 #9 [P2｜代码确认] 切换视图丢失资产探索的全部筛选上下文

- **位置**：`frontend/src/App.tsx` L50–58（视图条件渲染导致 Assets 卸载）；`Assets.tsx` 的 tab/筛选/排序/分页/勾选全部是组件局部 state。
- **复现步骤**：资产探索设置「公司=澄川云、来源=FOFA、第 2 页」→ 去关系图谱 → 返回资产探索 → 回到默认服务页签、筛选清空、第 1 页。
- **影响**：设计要求「切换视图时保留上下文」「切换视图不丢失筛选条件和选中对象」；当前仅 `selection.assetKey/domain` 经 store 存活，筛选全丢。
- **最小修复**：把 `tab/q/fCompany/fSource/fConf/fPort/fCdn/fLabel/sortKey/sortAsc/page/checked` 提升到 store（或 `sessionStorage` + `useSyncExternalStore`），Assets 挂载时恢复。
- **验收**：跨视图往返后筛选、页码、勾选保持。

### 问题 #10 [P2｜代码确认] 模态/抽屉焦点管理不完整：无焦点圈定、关闭后焦点不恢复、向导不支持 Esc

- **位置**：`AssetDrawer.tsx`（Esc ✓、初始聚焦 ✓、无 trap、关闭后焦点落 BODY——运行确认）；`TaskWizard`（无 Esc、无初始聚焦、无 trap）；`SearchModal`（同上，关闭后焦点落 BODY）。
- **影响**：审阅要求「模态抽屉的焦点进入、焦点约束、Esc 关闭和关闭后焦点恢复」四项，后三项不达标；键盘用户 Tab 会落入被遮蔽的背景内容。
- **最小修复**：三个弹层统一封装焦点管理：记录 opener、打开时聚焦、Tab 循环圈定（keydown 拦截首尾元素）、Esc 统一关闭、关闭后 `opener.focus()`。
- **验收**：抽屉内 Tab 循环不出容器；Esc 关闭后焦点回到触发按钮（运行检查 `focus_after_close` 不再是 BODY）；向导可 Esc 关闭。

### 问题 #11 [P3｜代码确认] 「查看筛选后的资产列表」按钮名不符实

- **位置**：`Overview.tsx` 近期资产变化区块按钮 → 仅 `navigate("assets")`。
- **复现**：点击后进入资产探索，显示 20 条全部资产，无任何「本轮新增」筛选（运行确认 count=20、公司筛选为空）。
- **最小修复**：携带快照差分键跳转（配合 #3 的口径修复），或改名「进入资产探索」。

### 问题 #12 [P3｜代码确认] 抽屉「相关关系」覆盖面依赖脆弱的节点 id 推导

- **位置**：`AssetDrawer.tsx` L31 `s:${host.split(".")[0]}${port}`——图谱服务节点仅 6 个（www443/api443/api9090/iot8443/dev8080/lab443），cloud/mail/vpn/oa/cdn-static/v6/裸 IP 资产全部显示「暂无图谱关系记录」，其中 cloud 明明存在 r11/r24 关联边（挂在域名/IP 节点上）。
- **最小修复**：按 `refId === assetKey` 匹配图谱节点（数据已带 refId），或直接按「域名→IP→服务」三级邻域聚合关系，而非字符串拼接 id。

### 问题 #13 [P3｜代码确认] 证据时间线把「最近观测：httpx 探测存活」写死在所有资产上

- **位置**：`AssetDrawer.tsx` 证据页签时间线末行固定文案；`iot:5683/udp`（CoAP，来源仅 Quake）、`dev:22`（SSH）等非 Web 资产也显示 httpx 探测。
- **影响**：观测事实与实际来源不符（审阅第 5 条「观测事实与结论的区别」）；演示字段冒充观测。
- **最小修复**：时间线末行改用 `sources` 最后一项与 lastSeen 生成；非 Web 资产显示「端口/引擎观测」。

### 问题 #14 [P3｜代码确认] fake-IP 判定用字符串前缀且两处实现不一致

- **位置**：`AssetDrawer.tsx` DNS 页签 `a.startsWith("198.1")`（会误命中 198.10–198.17 公网地址）vs `Assets.tsx` IP 页签 `ip.startsWith("198.18.")`（会漏 198.19.x）。正确范围是 198.18.0.0/15。
- **最小修复**：抽成共享的 `isFakeIp()`（按整数网段判断），两处引用。

### 问题 #15 [P3｜代码确认] 「复制」按钮在剪贴板不可用时仍提示已复制

- **位置**：`AssetDrawer.tsx` L37–40：`navigator.clipboard?.writeText().catch(()=>{})` 后无条件 `alert("已复制…")`。非安全上下文（http 非 localhost）下会假报成功。
- **最小修复**：在 then/catch 中分别提示成功/失败（并提供手动选择文本的降级）。

### 问题 #16 [P3｜代码确认] CSV 公式前缀转义比后端宽松

- **位置**：`services/csv.ts` L6 `/^[=+\-@]/` 未先 `lstrip` 空白；后端 `s8_report.py text_cell` 先去空白再判断，且清理控制字符。前端导出对 `" =cmd"` 类单元格不会转义。
- **最小修复**：对齐后端：先 trim 起始空白判断前缀、清理 `[\x00-\x08\x0b\x0c\x0e-\x1f]`。

### 问题 #17 [P3｜代码确认] 概览与报告中心的「待核对」口径随状态分叉

- **位置**：Overview 用 `pendingLeads.length`（状态感知），Reports 汇报视图用 `leads.length`（总数）。标记 1 条已复核后：概览 11、报告仍 12（运行确认）。
- **最小修复**：报告中心同样按待复核状态计数，或两处都标明口径（「待复核 N / 共 M」）。

### 问题 #18 [P3｜代码确认] 其他一致性问题（合并项）

- 图谱 r16 让悬空 CNAME 的 `legacy.example.com` 指向 `203.0.113.77`（lab 的 IP），与域名记录「NXDOMAIN、无选用地址」矛盾——悬空 CNAME 没有可到达的解析终点；r8 把纯「品牌相近」标成 `icp` 关系类型（证据自述「无备案交叉证据」）。
- 向导第 2 步「纳入范围」表对用户任意输入的种子也显示固定依据「ICP 备案主体一致」。
- fPort 筛选选项包含仅存在于 D+ 资产的端口（7547），选中后永远 0 结果。
- 域名页签搜索用原始大小写 `includes`，与服务页签的 lowercase 不一致。
- 「待核对」标签在资产表为红色（danger）、抽屉内为蓝灰（info），同一标签两套颜色语义。
- 复核 noteDraft 切换线索不清空，草稿会带到下一条线索。
- 面包屑在 openAsset/openLead 链路内保留，但 `navigate()`（如「在关系图谱中定位」）整体重置路径，调查路径跨视图即断。
- 快照 `newLeads: 7` 与 10-09 时间戳线索 9 条不符；资产/线索观测时间（13:59–14:37）晚于本轮运行 finishedAt（10:26）约 4 小时，证据时间线自相矛盾。
- 数据规模低于建议：域名 14/30–50、任务 2/8–12（设计提示词为「建议」，列为改进而非缺陷）。

---

## 4. 待验证问题（未取得证据，不计入缺陷）

- **V1 视觉观感与对比度**：`--ink-3 #6b7f8f` 于白底约 3.9:1、amber 徽章约 3.2:1，疑低于 WCAG AA 4.5:1（小字号）。需视觉模型或对比度实测工具确认。
- **V2 1920 视口**：仅验证了 390/1024/1440；1920 的密度与留白未测。
- **V3 图谱键盘可达性**：`<g role="button">` 无 tabindex，疑键盘不可操作；需键盘走查确认。
- **V4 触屏操作**：图谱仅实现鼠标拖拽/滚轮缩放，390px 下图谱的可用性需真机确认。
- **V5 打印布局**：`@media print` 规则存在，实际打印分页效果未验证。
- **V6 动效时长**：CSS 定义 120–200ms 区间，实际过渡帧感未验证（已确认 respects prefers-reduced-motion 与本地开关）。

---

## 5. 视觉、文案与交互改进建议（收益/代价/是否值得本轮）

1. **值得本轮**：修 #4（键盘搜索）与 #10（焦点管理）——纯交互正确性，代价小。
2. **值得本轮**：统一「隔离/待核实」视觉语言：IP/域名页签的 D+ 行加隔离色底纹与「隔离候选」徽章（配合 #5），让边界在所有表格可见。
3. **可延后**：数据规模扩充（域名→30+、任务→8+、双倍线索）：提升演示说服力，但工作量大，属内容生产而非缺陷。
4. **可延后**：Overview「建议优先核对」队列增加按 kind 的筛选 chips；复核工作台按线索类型分组。收益：高密度下的定位效率；代价：中。
5. **不建议本轮**：更换组件库/重做视觉主题。现有设计系统与设计提示词的视觉方向（雾白/墨蓝/青绿、紧凑密度、等宽字段）一致且执行到位，推翻无收益。

---

## 6. 必须保留的有效设计与业务规则（防退步清单）

- **隔离不可一键升级**：隔离页签提示与 Review 工作台「C 级候选不会被一键升级为可信资产」文案——修 #5/#8 时不得引入任何「确认后升级」捷径。
- **总表口径**：`Reports.tsx` master 严格来自 `trustedAssets()` 且表头与 `s8_report.py` HEADERS 完全一致（序号/资产/端口/标题/技术栈/等级标注/来源/置信度/截图链接）——保留。
- **置信度/严重程度双维度徽章**及 ConfBadge 的 title 说明；域名五类标注只作分类。
- **证据透镜三分栏**（原始观测/选用结果/采纳理由）与 DNS 页签的「多上游差异表 + fake-IP 异常标注 + 选用理由 + 已知问题警示」。
- **演示边界声明**：TopBar「演示数据」徽章、Sidebar「WSL 执行层：浏览器不可达」、向导行为说明、XLSX/HTML 禁用态与原因、CSV 文件名「演示数据导出」、截图「演示生成缩略图」水印——这些是本前端最重要的真实性护栏，任何修改不得移除或弱化。
- **数据服务层收口**：所有视图经 `useStore()`，替换为后端时只动 `store.tsx`——保留该架构。
- **来源页六级能力徽章体系与「未运行/无错误/未提供」的三态区分**——只需修正 #2 的错误数据，不要简化成统一绿灯。
- **响应式骨架**：390 底部导航 + 全屏抽屉 + 表格横滚，1024 图标侧栏——已验证工作正常。

---

## 7. 最小修复清单

**本轮必修（P1/P2）**：
1. #1 重复主键资产（数据建模 + 统一派生源）
2. #2 来源页能力误述（dataset 数据修正）
3. #3 新增资产口径与两视图数字统一
4. #4 键盘 Enter 搜索抽屉闪退
5. #5 IP/域名页签隔离边界与静默点击
6. #6 任务状态三处矛盾（mkStages、advanceTask、allTasks 去重）
7. #7 localStorage 畸形数据白屏
8. #8 TRUSTED_CONFIDENCE 对齐 precision.py（含 192.0.2.10:8081 归属口径）
9. #9 筛选上下文跨视图保留
10. #10 焦点圈定/恢复/向导 Esc

**可延后（P3）**：#11–#18（按钮名不符实、节点 id 推导、时间线写死、fake-IP 判定、复制假成功、CSV lstrip、待核对口径分叉、图谱边语义与数据时间线等合并项）。

---

## 8. 实际检查记录

**执行的命令与结果**：
- `npx tsc -b` → exit 0（类型检查通过）。
- `npm run build` → `tsc -b` 通过后 `vite build` 失败：esbuild 服务子进程 `spawn EPERM`（审阅沙箱命名管道限制，非项目缺陷；作者侧 dist 产物 2026-10-10 17:20:06 晚于 src 最后修改 16:33:46，构建产物为当前源码）。
- `python scripts/review_frontend_verify.py`（链路 A + 附加检查）、`…verify2.py`（任务/向导/持久化）、`…verify3.py`（搜索/窄屏/重置/localStorage 容错）、`…verify4.py`（键盘搜索全视图矩阵、畸形数据、图谱、重置）、`…probe.py`/`…probe2.py`（Enter 路径根因定位，MutationObserver + 点击坐标捕获）、`…recheck.py`（来源页徽章、报告总表、页签计数复核，结果落盘 `docs/audits/review-artifacts/recheck-dump.txt`）。服务方式：`http.server` 托管 `frontend/dist` 于 127.0.0.1:6271，Chromium 无头 1440×900 / 1024×768 / 390×844。
- 产物：`docs/audits/review-artifacts/*.png`（18 张过程截图 + 导出的 `chainA-export.csv`、`report-master-export.csv`、runtime-results*.json）。

**操作链路**：
- 链路 A 全程：概览(19/14/12/7) → 优先队列 L001 → 证据工作台（观测事实/来源/时间/紧急程度/置信度分列）→ 打开关联资产 → 证据透镜三分栏 → DNS 页签（198.18.0.23 标记 fake-IP 异常观测）→ Web 与截图（演示缩略图标注）→ Esc 关闭 → 资产探索（公司=澄川云 + 来源=FOFA → 4 条）→ 导出当前结果 CSV（5 行含表头，含重复主键 cloud×2）。
- 链路 B 全程：RUN-20261009-01 → 重试 gowitness（结果数 3、日志追加）→ 模拟推进（8/8 已完成，但 report 子任务悬挂、任务卡片重复）→ 向导四步创建 DEMO 任务 → 刷新（demoTasks/备注均持久化）→ 重置演示（localStorage 清空、指标回到 19/14/12/7）。
- 附加：键盘搜索矩阵（4 视图 × Enter 全失败 + 点击成功）、域名/IP 页签隔离绕过、cloud 双行抽屉 IP 错配、报告八表与 master CSV（19 行、无 D+、无重复 host|port）、来源页徽章、390/1024 视口 DOM 测量（drawer 宽 390px、表格 scrollWidth 889>429、侧栏底部化 79px）、localStorage 非法 JSON（可恢复）与畸形结构（白屏+持久）。

**未检查项与原因**：
- 真实视觉/对比度/动效观感——当前环境无图像输入能力，截图已存档待人工或视觉模型复核（V1–V6）。
- 1920 视口、打印输出、触屏——未列入脚本，原因同上/无触屏设备。
- `npm run dev` 热更新路径——dist 静态验证已覆盖运行行为，未重复。
- `office-*` 技能不适用（无 Office 交付物）。

**明确声明**：构建与类型检查通过 ≠ 视觉与业务验收通过；上述运行结论仅覆盖列出的路径与视口。

---

## 9. 可直接交回 Kimi K3 的修正提示词

> 你此前交付了 ASM Workbench 前端（`frontend/`，React+TS+Vite）。独立审阅已完成（静态审读 + tsc 通过 + Playwright 于 dist 构建实测链路 A/B），确认了一批需要修复的问题。请按下述清单做**最小修改**：只改 `frontend/src` 与必要的使用说明；继续遵守原设计提示词的全部约束（不执行真实扫描、不调用第三方 API、不冒充连接 WSL、D 级永不进入可信统计与总表、置信度与严重程度分离、演示扩展字段明确标注）。不要重构整体架构、不要更换视觉主题、不要动 `frontend/` 以外的任何文件。
>
> **必修问题（引用编号）：**
>
> 1. **[R1] 重复主键资产**：`data/dataset.ts` 中 `cloud.example.com|443|tcp` 存在两条（198.51.100.21 / .22）。后端契约为 `UNIQUE(host,port,proto)`。请把第二个 CDN 节点改为同一资产的补充信息（如 `alternateIps` 或证据条目），删除重复资产行与快照里的 `cloud.example.com|443|tcp#2` 伪键。验收：资产表搜索 cloud 仅 1 行；「服务资产」页签计数 = 概览「可信资产」数；导出 CSV 与报告总表主键无重复；总表该行保留 .21 的已采集截图状态。
> 2. **[R2] 来源页能力误述**：`data/dataset.ts` sources 中 FOFA 含 `online-verified`（事实：凭据全空，从未实网验证）；naabu/httpx/gowitness 标 `integrated`+`inMainFlow`（事实见 docs/OPERATIONS.md：三者均未接入主流程，端口扫描为 nmap、Web 探测为 Windows Python httpx、截图为 Windows Playwright）。请改为真实状态：FOFA 保留 installed/adapter/integrated/offline-verified；三个 WSL 工具去掉 integrated 与主流程徽章，note 写明「已安装，未接入主流程」及当前由谁承担该阶段；任务子任务（`tasks` 数据）的工具名同步改为 nmap / httpx（Windows） / Playwright 截图，或在演示任务中明确标注「演示工具名」。保留来源页的六级徽章体系与顶部警示条。
> 3. **[R3] 新增资产口径**：概览「本轮新增资产」当前把 2 个 D+ 隔离级资产计入（=7），报告中心却显示「约 8 个」（把 `#2` 伪键也数进去）。请让两处使用同一差分函数，且只统计可信资产：改为「本轮新增可信资产 N（另有 X 条 D+ 待核实）」；同时把 10-09 的线索时间戳与快照 `newLeads` 对齐（当前 9 条线索 vs 记 7），把资产/线索观测时间改为早于 run 的 finishedAt（当前晚 4 小时）。验收：两视图数字一致、可追溯、D+ 不计入。
> 4. **[R4] 键盘搜索跳转失效**：SearchModal 中 ↑↓ 选择后按 Enter，抽屉会渲染又被同一次按键的 keyup 立即关闭（抽屉挂载时自动 focus 的关闭按钮吃到了 Enter keyup 的合成 click，坐标 (0,0)）。修复：Enter 分支加 `e.preventDefault()`，并让 AssetDrawer 的初始聚焦延迟一帧或聚焦 `tabIndex=-1` 的容器。验收：Ctrl+K → ↓ → Enter 后抽屉保持打开、焦点在抽屉内；Esc 关闭后焦点回到搜索触发按钮。
> 5. **[R5] 隔离边界绕过**：IP 页签包含 192.0.2.200 / 198.51.100.50（D+ 资产 IP）且点击会打开其详情；域名页签点击 `shop.example.org` 也打开 D+ 资产详情；点击 `iot.example.com`（无 443 资产）无任何反应。请让 IP/域名页签同样基于 `TRUSTED_CONFIDENCE` 过滤后的资产生成；域名行改为进入「该域名筛选后的资产列表」而非拼 `domain|443|tcp` 魔法键；无资产域名显示「无资产记录」且不可点击。D+ 资产只允许从隔离页签和线索工作台进入。
> 6. **[R6] 任务状态矛盾**：a) `mkStages` 的 `failedAt` 参数因条件顺序永远不生效（`i < upto` 先命中）——修正判定顺序，让 RUN-20261009-01 的 s7（Web 识别与截图）为 failed、s8 为 pending，与「部分失败」状态及 gowitness 失败子任务一致；b) `advanceTask` 只翻转 running 子任务——推进阶段时同步处理对应子任务（failed→done、pending→running），全部完成时归位 report 子任务；c) `allTasks` 合并 `[...demoTasks, ...seedTasks]` 不去重——按 id 去重（demoTasks 覆盖同 id 种子任务），消除列表中同一 run 出现两张不同状态卡片的问题。验收：partial-failed 任务在阶段流程可见 1 项失败；推进至 8/8 后无悬挂子任务；每个 run_id 仅一张卡片；重试后 gowitness 结果数 +3（现状保留）。
> 7. **[R7] localStorage 容错**：结构合法但字段缺失的数据（如 `demoTasks:[{id,name}]`）会让 Overview `t.stages.filter` 抛错、整页白屏且无法通过 UI 恢复。请：`loadLocal` 对合并结果做逐字段校验/归一（demoTasks 逐项校验、leadStatus 白名单过滤），非法即回退默认并清键；并加顶层 ErrorBoundary 渲染「本地演示数据损坏 → 一键重置」入口。验收：注入上述坏数据后应用可渲染、可一键重置。
> 8. **[R8] 可信口径对齐后端**：`TRUSTED_CONFIDENCE={A,B,C,E}` 与 `asm/precision.py` 不一致（后端：A/B 入 assets；C 需 ≥2 独立来源佐证；E/F 一律隔离）。请实现镜像规则：C 仅当 `sources.length>=2`（或显式 corroborated 标记）计入可信，否则按隔离展示；E/F 一律隔离；把 192.0.2.10:8081（cid=null、线索明言归属未知）从可信统计剔除（降为 D 待归属）。同步更新 Overview 口径脚注与 dataset 注释（当前注释「与后端语义对齐」不实）。验收：单来源 C 与无归属资产不计入可信；脚注与 precision.py 一致。
> 9. **[R9] 筛选上下文保留**：切换视图再返回后，资产探索的页签/搜索/组合筛选/排序/分页/勾选全部丢失（App.tsx 条件渲染卸载 Assets）。请把这些状态提升到 store 或会话级存储并在挂载时恢复。验收：跨视图往返后筛选、页码、勾选保持。
> 10. **[R10] 焦点管理**：AssetDrawer/SearchModal/TaskWizard 统一补齐：焦点圈定（Tab 不出弹层）、关闭后焦点恢复到触发元素、向导支持 Esc 关闭（现状仅抽屉有 Esc、关闭后焦点落 BODY）。验收：抽屉内 Tab 循环；Esc 后焦点回触发按钮；向导可 Esc 关闭。
>
> **可延后的小修（有余力再做，不做不阻断）**：概览「查看筛选后的资产列表」按钮名不符实（未携带筛选）；抽屉「相关关系」用 `s:{label}{port}` 拼节点 id 导致多数资产为空，应按 refId 匹配；证据时间线把「httpx 探测存活」写死在非 Web 资产上；fake-IP 判定 `startsWith("198.1")` 应改为 198.18.0.0/15 网段函数并统一两处实现；复制按钮失败时仍提示成功；CSV 公式前缀转义未像后端一样 lstrip 空白；概览与报告中心「待核对」口径分叉；图谱 r16（悬空 CNAME 指向 lab IP）与 r8（品牌相近标为 icp 关系）语义修正；向导范围表对任意种子输入显示固定「ICP 备案主体一致」依据。
>
> **不得改动的既有正确行为**：隔离候选不可一键升级；报告总表严格来自去重后的可信资产且表头保持 序号/资产/端口/标题/技术栈/等级标注/来源/置信度/截图链接；置信度与严重程度双维度徽章；证据透镜三分栏与 DNS 异常观测标注；全部演示边界声明（演示数据徽章、WSL 不可达、禁用按钮原因、演示导出命名、截图水印）；数据服务层收口架构；390/1024 响应式骨架。
>
> **交付要求**：完成后给出修改文件清单、每项问题的验收结果（对照上面各条验收标准逐条说明如何在浏览器中验证）、`npm run build` 与 `tsc -b` 的输出结论；重跑两条演示链路（概览→L001→证据透镜→DNS→筛选→导出；新建任务→模拟失败→重试→刷新→重置）并说明结果。不要新增依赖，不要改 `frontend/` 之外的文件（README/使用说明的必要更新除外）。

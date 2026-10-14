# ASM Workbench 前端

「以证据为核心的暴露面调查工作台」——墨蓝侧栏 + 雾白工作区 + 青绿强调色。
React 18 + TypeScript + Vite 单页应用。默认入口为真实工作台项目中心，`?demo=1` 为虚构演示，`?pilot=1` 为独立的历史调查档案页。

2026-10-11 项目整理：默认显示业务调查，测试/演示单独分类；项目支持卡片、列表、表格、搜索与排序。历史证据统一实际调查对象上下文，支持来源筛选、全文搜索、分页、表格/列表、详情、CSV 和完整 HTML 导出。目录分类、后续验收数据隔离及保留旧证据引用的规则见 [项目整理说明](../docs/PROJECT_ORGANIZATION.md)。下面的演示链路和演示数据约定适用于虚构演示入口。

## 启动

```powershell
cd frontend
npm install --cache .\.npm-cache   # 沙箱环境下建议指定仓库内缓存
npm run dev                        # http://127.0.0.1:6100（5173 段在部分系统端口排除范围内）
npm run build                      # 类型检查 + 产物构建（dist/）
npm run preview                    # 预览构建产物 http://127.0.0.1:6200（4173 在 4136–4235 排除段）
```

> 若全局 npm 缓存目录不可写（沙箱），请加 `--cache .\.npm-cache`；
> 若环境拦截生命周期脚本，追加 `--ignore-scripts`（本依赖树不需要安装期脚本）。

## 演示链路（验收路径）

1. 打开 **项目概览** → 「建议优先核对」点击 `L001 lab.example.com DNS 冲突`
2. 进入 **证据复核** → 查看观测事实与证据来源 → 「打开关联资产详情」
3. 抽屉中切到 **证据** 页签 → 证据透镜：原始观测 / 选用结果 / 采纳理由
4. 切到 **DNS** 页签 → 多上游差异，198.18.0.23 标记为 fake-IP 异常观测
5. 进入 **资产探索** → 组合筛选「公司=澄川科技 + 来源=FOFA」→ 导出当前结果 CSV
6. 回到复核 → 添加备注 → 标记已复核（localStorage 持久化）
7. **调查任务** → 新建调查（四步向导，创建演示任务）→ 模拟推进 / 重试失败子任务
8. **关系图谱** → 点击节点聚焦邻域，双击服务节点打开同一资产抽屉
9. **报告中心** → 工程明细 → 八张表预览 → 下载 CSV（演示数据导出）

## 目录结构

```
src/
  types/index.ts        类型定义（对齐 asm/models.py 语义；演示扩展字段有注释）
  data/dataset.ts       统一虚构数据集（澄川科技集团）
  data/tkcnEvidence.ts        被动证据载入桩（入库安全；glob 载入生成的 .local 文件）
  data/tkcnEvidence.local.ts  真实被动试点数据（生成文件，含目标真实数据，gitignore 排除不入库）
  services/store.tsx    数据服务层 + 本地状态（localStorage 持久化、重置演示）
  services/csv.ts       CSV 导出（引号/换行/中文/公式前缀转义）
  services/passiveReport.ts  被动试点单文件 HTML 报告导出（含 2 张内嵌截图，离线可开）
  components/           侧栏、顶栏、上下文条、搜索、面包屑、抽屉、截图、徽章、图标
  views/                概览 / 资产探索 / 调查任务 / 证据复核 / 关系图谱 / 数据来源 / 报告中心 / 被动试点
```

## 数据与真实性约定

- 全部数据为**虚构演示数据**：域名限 `example.com/example.org`，IP 限文档保留段
  （192.0.2.0/24、198.51.100.0/24、203.0.113.0/24），fake-IP 异常观测用 198.18.0.0/15
  （`isFakeIp()` 按整数网段判断，不误伤相邻公网段）。
- 可信资产统计口径镜像后端 `asm/precision.py` 的 `destination()`：**A/B 可信；C 需 ≥2 独立来源
  佐证才计入；D/D+/E/F 一律隔离**，永不进入可信统计与总表。主键 `host+port+proto` 唯一，
  多来源命中不重复计数；同一 host 的多个解析地址并入单条资产的 `alternateIps` 展示。
- 演示数据当前规模：5 企业 / 14 域名 / 15 可信资产 / 3 条 D 级隔离候选 / 12 条待核对线索。
- 置信度 A–F 与风险严重程度是两个维度；域名五类标注是资产分类，不是风险评分。
- 快照对照、复核备注、操作历史、模拟任务为**演示扩展能力**，仅持久化在 localStorage；
  「重置演示」按钮可一键还原；损坏/旧版本地数据会被逐字段校验归一，异常时由顶层
  ErrorBoundary 提供一键重置，不会白屏。
- 来源页能力分级与 `docs/OPERATIONS.md` 对齐：六家引擎中 **FOFA 已配置凭据并完成一次受控被动试点**
  （2026-10-10，11 次请求 / 0 F 点 / 限速 ≥20s，见「被动试点」视图与 `report/tk.cn_delivery/`），其余五家未配置；
  naabu / WSL httpx / gowitness 已安装但**未接入主流程**——当前端口扫描为 nmap（Stage 6）、
  Web 探测为 Windows Python httpx、截图为 Windows Playwright（Stage 7）。
- 前端**不执行真实扫描、不调用第三方 API、不执行 shell**，浏览器未连接 WSL。
  例外：**被动试点视图**展示的是「已由后端脚本收集并固化为静态数据」的真实被动证据
  （`data/tkcnEvidence.local.ts` 由交付目录自带的工具
  `report/tk.cn_delivery/tools/tkcn_build_dataset.py` 从 `evidence/` 聚合生成；
  **含目标真实数据，不入 git**——入库的 `tkcnEvidence.ts` 只是无数据回落桩，
  fresh clone 下该视图显示「未载入证据」空态属预期），
  视图本身仍零网络请求；其导出的 HTML 报告为纯本地 Blob 下载。
- **被动试点（tk.cn）真实证据口径**：目标处于未授权阶段，全部条目为候选（candidate_only），
  绝不计入可信资产统计；范围外命中（邻域/集团/供应商/疑似仿冒）单列展示，绝不混入候选。
  收集全程零发包：DNS 仅查询公共递归解析器，搜索引擎仅 fofa.info API（限速 ≥20s、当日熔断 12 次）。

## 被动试点视图（真实证据，只读展示）

- 入口：侧栏「被动试点」；数据为交付目录自带工具 `report/tk.cn_delivery/tools/tkcn_build_dataset.py`
  聚合的真实被动证据（`.local.ts` 生成文件，不入库；无数据时视图显示空态与生成指引）。
- 五个分区：候选资产（host+port 去重）/ DNS 多上游观测 / 邻域与反馈线索 / 子域（三源并集）/ 查询台账。
- 「导出 HTML 报告」生成单文件报告（含 2 张本地渲染证据截图，base64 内嵌，离线可开）；
  验证工具 `report/tk.cn_delivery/tools/tkcn_pilot_verify.py` 会把导出捕获落盘到交付目录 `report/tk.cn_delivery/report.html`。
- 完整交付（样表格式 + 证据 + 工具调用痕迹 + 限速账本）见 `report/tk.cn_delivery/`
  （该目录含真实目标数据，已在 `.gitignore` 排除）。
- 暂停/终止任务、XLSX/HTML 报告下载等后端尚无能力：展示为禁用或「待接入」，不空点成功。
- 键盘可达性：Ctrl/Cmd+K 全局搜索（↑↓ 选择，Enter 跳转）；抽屉/搜索/向导均支持 Esc 关闭、
  焦点圈定（Tab 不出弹层）与关闭后焦点恢复。

## 独立审阅修复记录（GLM 5.3 审阅 → Kimi K3 修复）

依据 `docs/audits/GLM_5_3_FRONTEND_REVIEW_REPORT.md` §9 的 R1–R10 做了最小修复，仅改动 `frontend/src`：

- **R1** `cloud.example.com|443|tcp` 重复主键：第二 CDN 地址并入 `Asset.alternateIps`，
  数据集/快照/导出/总表统一从去重后的可信集派生。
- **R2** 来源页能力误述：FOFA 去掉「实网已验证」，naabu/WSL httpx/gowitness 改为
  「已安装，未接入主流程」并注明当前承担者（nmap / Windows httpx / Windows Playwright）；
  任务子任务工具名同步为真实引擎。
- **R3** 「本轮新增资产」口径：概览与报告中心共用 `diffNewAssetKeys()` 返回的 `added/removed`，只统计可信资产，
  不再混入 D+ 与「约」凑数；10-09 观测时间全部移入运行窗口（10:00–10:26Z）。
- **R4** 键盘 Enter 搜索跳转闪退：Enter 分支 `preventDefault()` + 抽屉初始聚焦延迟一帧。
- **R5** IP/域名页签隔离边界：两页签同样按 `isTrustedAsset()` 过滤；域名行进入
  「该域名筛选后的资产列表」，D/D+ 不再被当作常规资产打开。
- **R6** 任务状态三处矛盾：`mkStages` 对失败后的全部阶段强制 pending（初始 s7 failed/s8 pending），
  `advanceTask` 同步推进子任务、`allTasks` 按 id 去重。
- **R7** 畸形 localStorage 白屏：`loadLocal` 逐字段校验归一 + 顶层 ErrorBoundary 一键重置。
- **R8** 可信口径：`isTrustedAsset()` 镜像 `precision.py`（C 需双来源；E/F 隔离），
  192.0.2.10:8081 降为 D 待归属；可信资产数 19 → **15**。
- **R9** 资产探索筛选状态提升到 store，跨视图往返保留页签/筛选/排序/分页/勾选。
- **R10** 抽屉/搜索/向导统一 `useFocusTrap`：Tab 圈定、Esc 关闭、关闭后焦点恢复。

附带小修（审阅 P3 中低成本项）：#11 按钮更名「进入资产探索」、#12 相关关系按 refId 匹配、
#13 证据时间线不再写死 httpx、#14 fake-IP 判定统一为 198.18.0.0/15 网段函数、
#15 复制失败时降级为手动选择、#16 CSV 公式前缀转义对齐后端 lstrip。

验证：`npx tsc -b` 与 `npm run build` 均通过；`scripts/fix_frontend_verify.py`
（Playwright 无头 Chromium，本地静态服务 dist）重跑链路 A/B 与 R1–R10 定向验收，
**53/53 通过**，截图与结果存于 `docs/audits/review-artifacts/fix/`。

## 本轮 N1–N8 回归

颜色令牌按 WCAG AA 加深；小屏网格允许收缩，宽表在自身容器滚动。初始失败任务的后续阶段没有运行时间戳，
所有阶段时间使用有效 ISO 8601。快照差分同时展示新增与「离开可信集」，离开不等同于资产消失。
资产原始记录的工具前缀按 Web/服务来源选择；空表跨度跟随可见列；域名可信判定复用
`isTrustedConfidence(confidence, sources)`，无需伪造 Asset 类型。

在 PowerShell 7 中构建后运行 `node scripts/frontend_data_regression.cjs` 与
`.\.venv\Scripts\python.exe scripts/frontend_n1_n8_verify.py`。脚本仅访问本地静态构建；结果写入
`data/qa/frontend-n1-n8/`。当前轮结果以脚本新产物为准，上述历史 53/53 不计为本轮验收。

## 未来需要的后端接口（建议契约，当前不存在）

| 方法 | 路径 | 说明 | 优先级 |
| --- | --- | --- | --- |
| GET | `/api/projects` | 项目列表与范围摘要 | 高 |
| GET | `/api/projects/{id}/assets?filter=…` | 资产分页查询（host+port+proto 主键） | 高 |
| GET | `/api/assets/{key}/evidence` | 证据透镜数据：原始观测/选用结果/采纳理由 | 高 |
| GET | `/api/runs/{run_id}` | 任务阶段、子任务、计数与日志 | 高 |
| GET | `/api/leads` / PATCH `/api/leads/{id}` | 待核对线索读写（当前仅本地演示） | 中 |
| GET | `/api/snapshots/diff?a=…&b=…` | 运行快照对照（新增/字段变化/新待核对） | 中 |
| GET | `/api/graph?root=…&depth=…` | 局部关系图（类型/状态筛选） | 中 |
| GET | `/api/reports/{run_id}/{table}.csv` | 八表 CSV；XLSX/HTML 复用现有生成器 | 中 |
| WS | `/api/runs/{id}/events` | 实时进度（当前轮询/手动刷新即可） | 低 |

替换方式：仅改 `src/services/store.tsx`，组件不感知数据来源。

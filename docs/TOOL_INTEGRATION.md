# 已有工具的完整流程接入

范围确认：2026-10-12。本批覆盖已有工具、六家搜索引擎、Chrome运行时和SecLists字典；Amass、gau、waybackurls、LinkFinder、arjun、x8留到下一批。

## 流程与分工

| 阶段 | 工具 | 结果衔接 |
|---|---|---|
| 被动调查 | FOFA、Quake、Hunter、ZoomEye、Shodan、Censys；subfinder、OneForAll、CT/CDX索引 | 独立来源候选、合并来源与证据，范围内域名进入DNS；范围外保留线索 |
| DNS核实 | dnspython、dnsx、dig | 按域名/记录类型/显式上游独立动作；CNAME范围复核与fake-IP拒绝；批准IP进入端口探测 |
| 端口与服务 | Nmap、Masscan、naabu、a_scan | TCP发现可独立选工具；UDP/版本/NSE各自独立权限；HTTP常见端口及HTTP服务生成明确URL入口 |
| Web识别 | Python httpx、ProjectDiscovery httpx | 状态、标题、技术线索及响应证据；进入页面/爬取/路径等已选能力 |
| 页面证据 | Playwright、gowitness + WSL Chrome | PNG与原生元数据进入证据索引及报告 |
| URL及路径 | native_crawler、katana、stage_7_paths、ffuf | 原始URL候选；ffuf随机基线及二次HTTP复核；同源路径不重启整站爬取 |
| 暴露与风险 | 内置响应头/CORS/路径核查、wafw00f、nuclei | wafw00f须选 `waf_fingerprint`；nuclei须明确本地批准模板；结果为待复核候选 |
| 输入资源 | SecLists固定commit字典 | 校验commit及文件blob，冻结入运行回执；DNS/内置路径/ffuf共用资源选择 |
| 交付 | 既有共享事实及快照引擎 | 日志、原始输出、证据hash、覆盖缺口及专业/用户版CSV、HTML、Markdown |

## 本次代码接入

`asm/external_tools.py`统一外部适配器，`tools/http_tool_runner.py`为WSL HTTP工具运行器。工作台注册表按能力/工具路由；`profiles/modes.yaml`列出真实候选，已有前端通过模式目录显示新增工具。

- 所选工具各建独立步骤，拥有参数快照、动作回执、原生输出及报告来源；单源失败不吞掉其他来源。
- `tool_options`支持同一能力下不同工具的参数覆盖；计划预览与实际队列使用相同有效参数。
- OneForAll复用隔离白名单runner，live job和留档导入均保留；每次校验全套被动flags，不恢复旧Stage job绕过权限。
- HTTP工具在仅有loopback的私有network namespace中运行，显式代理经stdin/stdout交由Windows执行请求。每个请求、重定向和浏览器子资源走现有范围、物理预算与回执；工具没有直接目标网络出口。
- 范围契约（Session 009 加固并测试固定，`tests/unit/test_broker_scope.py`）：运行器只转发 GET/HEAD 的 http/https，其它方法与协议在代理侧直接 405/501，绝不下发；每个请求都经 `broker_request()` 交回 `ExecutionContext.http`，因此与内置采集共用同一授权范围、同一每主机物理预算账本和同一回执。**越界主机不产生传输**：HTTPS 的 CONNECT 只允许本任务目标主机（其它主机 403），明文 HTTP 请求由范围判定拒绝，工具得到 403、任务记录 `scope_blocks`（`outside_function_scope`）而不是一条观测。预算耗尽或授权被撤回会抛出 `PolicyDenied` 让任务失败，不会被伪装成远端 4xx。broker 发出的请求在物理账本中标记 `transport=isolated_http_broker`，与工作台自身的 `target_http` 请求可区分。katana 的 crawl-scope 是精确的 `scheme://host:port` 正则（`external_tools.crawl_scope()`），不会放宽到近似域名、其它端口或其它协议。
- 明文 HTTP 与 HTTPS 的差别是刻意的：HTTPS 隧道按任务目标主机固定，明文请求则允许任何**已在授权范围内**的主机（同站不同端口/协议、范围内跳转属预期采集行为），但每一次都同样过范围、预算与回执；范围外一律 403。
- HTTPS在本地代理终止并经Windows校验上游TLS。代理证书不作为目标TLS资产；TLS事实由 `native_tls` 独立采集。Chrome仅信任该任务代理证书的固定SPKI；其无sandbox启动仅位于私有user/network namespace。原WSL的gorod驱动已完成真实PNG验收；chromedp在本机隔离环境观察到超时，默认gowitness使用gorod/60秒，不改装Chrome。
- 当前外部HTTP工具仅支持有界GET/HEAD观察。POST/raw、DNS/TCP/code/headless/JS等nuclei模板类型及Interactsh未开放；需求超出此适配器范围会明确拒绝，不记录为已检测。
- 同站不同端口/协议可以继续Web核实；已爬取同源的路径不再作为新整站起点，保持深度及请求预算。

## 配置示例

在完整模式项目中使用多工具选择，不填写凭据：

```yaml
plan:
  selection: custom
  selected_capabilities: [tcp_scan, dns_recursive, web_visit, web_crawl, web_path_enum, screenshot, vulnerability_check]
  selected_tools: [nmap, masscan, naabu, a_scan, dnspython, dnsx, dig_probe, target_http, httpx, katana, ffuf, gowitness, nuclei, wafw00f]
  params:
    tcp_scan:
      ports: "80,443,8080,8443"
      split_batches: true
      batch_size: 512
    web_path_enum:
      dictionary: seclists:web_directories
    vulnerability_check:
      tool_options:
        nuclei:
          approved_templates: [templates/approved-observation.yaml]
        wafw00f:
          approved_checks: [waf_fingerprint]
```

项目仍需独立功能权限、范围及授权窗口。`tools.<能力>`和显式 `engine` 为单工具覆盖；要运行同能力多个工具时使用 `selected_tools`，避免同时设置冲突的单工具覆盖。

字典资源：`seclists:dns_top5000`、`seclists:web_directories`、`seclists:web_files`、`seclists:web_words`、`seclists:web_extensions`。nuclei当前只接受仓库内明确批准的HTTP观察模板文件；不自动下载/执行整库模板。

## 验收状态与剩余工作

本批本地/离线专项：73通过，证据 `data/validation/external-tools-20261012.xml`；包含10项新增适配器/代理/报告/恢复测试及既有DNS、Web、截图、爬取、多来源回归。全单元回归317通过，证据 `data/validation/tool-integration-unit-all-20261012.xml`。Ruff通过。新增工具的真实WSL执行单独验收，不能将替身验证记为工具实跑。

原 `Ubuntu` 实跑证据：`data/validation/native-tools-live-20261012-150726/summary.json` 的dig/dnsx、naabu/a_scan/Nmap五项均completed且观察到自有夹具；`data/validation/external-tools-live-20261012-150458/summary.json` 的httpx、ffuf、katana、wafw00f、nuclei五项completed；gowitness早期退出0但无PNG的误判已修复，最终以 `data/validation/external-tools-live-20261012-151602/summary.json` 的gorod实跑为准，真实PNG1280×720已视觉核对并纳入双报告。原工具版本/commit及a_scan哈希再次核对未改变，记录 `data/validation/original-wsl-tools-20261012.txt`。最终相关回归90通过：`data/validation/original-wsl-final-20261012.xml`；包含空发行版列表不得自动创建WSL、默认复用Ubuntu、无图退出0不得算截图完成。

尚未完成的外部验收：真实提供商账户及公开被动来源、OneForAll新live job、Masscan的实际网络接口、Nmap服务/UDP/NSE、外部白名单及更广HTTPS浏览器路径。代码接入和上述回环通过不代替这些验证。原有历史验收仍保留独立来源与日期。

Session 009（2026-10-14）专项：新增 `tests/unit/test_broker_scope.py` 32项，离线与回环固定范围契约——crawl-scope 精确性（不接受近似域名/其它端口/其它协议）、GET/HEAD 转发与回执、越界 URL 得到 403 且不产生观测、预算耗尽与授权撤回必须让任务失败、其它方法/协议被拒、产物名白名单（拒绝 `screenshots/../evil.png` 等路径穿越）、跨主机 CONNECT 在询问协调器之前即被拒、`scope_blocks` 进入工具回执记录，以及用真实 Workbench + 回环夹具证明在范围请求确实落账为 `isolated_http_broker`、越界请求零到达、预算耗尽时账本为 `started`+`blocked`。本批同时把原先内联在 `_http_job` 中的越界判定与产物名校验提取为可测函数（`broker_request()`、`BROKER_ARTIFACT`、`crawl_scope()`），行为不变。证据 `report/validation/broker-scope-unit.xml`。

原WSL已核实：默认发行版 `Ubuntu`、WSL2，用户 `longchuanli`，工作区 `/home/longchuanli/asm-ws`；已有工具、Chrome、util-linux/iproute2/openssl及固定commit字典均在，直接复用。受限进程先前返回空发行版列表，属于错误的环境判断；正式主机权限下列表才可用于此处核对。误新增的独立 `Ubuntu-24.04` 已停止部署并终止，不自动删除发行版、不迁移原数据、不切换默认发行版。

`scripts/inspect_tool_runtime.py`只读检查原环境；`scripts/prepare_tool_runtime.py`只部署选定的已存在发行版，默认复用 `Ubuntu`，不可见时明确报错，永不自动创建或注销WSL。已有环境不需要重装；安装/升级依赖应按具体缺项处理。

在原环境执行自有loopback验收，逐项验证外部工具依赖、取消/撤权及原生结果解析。`scripts/external_tool_acceptance.py`专测六个HTTP工具；结果进入独立验证工作区及WSL新建的 `results/workbench-*` 目录。

```powershell
.\.venv\Scripts\python.exe scripts/inspect_tool_runtime.py --distro Ubuntu
$env:WSL_DISTRO = 'Ubuntu'
.\.venv\Scripts\python.exe scripts/external_tool_acceptance.py --distro Ubuntu
```

重启后端时使用实际 `WSL_DISTRO`；搜索引擎账户、真实提供商响应及外部白名单验收需各自实际输入，不因安装完成而自动视为通过。

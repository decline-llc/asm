# 实施记录

## 2026-10-14 · Session 010 · katana JS 端点爬取面、工具版本矩阵，以及一轮文档债清理

- 用户指令「继续」。按 A 方向（可离线验收、不产生实网流量）推进 Web 阶段剩余缺口，并顺手处理了核实过程中暴露的大面积文档过期问题。
- **1) katana JS 端点爬取面（COVERAGE 的「JS 端点」缺口）**：新增 `external_tools.js_crawl_enabled()`——默认开启、`tool_options.katana.js_crawl: false` 可显式关闭、`jsluice` 请求**明确拒绝**（需要本适配器不提供的第三方二进制）、非布尔值报错；`tools/http_tool_runner.py` 只按 `spec["js_crawl"]` 追加 `-jc`，unset 时**不**默认开启，避免 WSL 侧自行发明策略。JS 解析仍在精确 `-cs` scope、`-dr`、`-duc`、限速与 broker 每请求范围/预算/回执之内。默认开启的理由写在 TOOL_INTEGRATION：适配器只允许有界 GET/HEAD，且每个请求都过同一治理路径。
- **2) 工具版本矩阵（此前只存在于被 Git 忽略的证据里）**：新增 `docs/reference/tool-versions.md`，把「版本 + 集成状态 + 接入位置 + 证据」收敛为一份可核对的矩阵，二进制版本以 `tools/tool-lock.json` 为唯一来源；新增 `tests/unit/test_tool_reference_docs.py` **4 项**强制：矩阵版本必须与 tool-lock 一致、集成状态必须取自受控词表、`external_tools.SUPPORTED` 里的每个工具都必须在矩阵中出现且不得标为「未接入」、每个已接入工具的 reference 页不得再出现过期的接入断言且必须正面写明「已接入」。
- **3) 文档债清理（本批主要工作量）**：按代码核实，参考文档与 `docs/OPERATIONS.md` 的工具总表长期把**已经接入**的工具写成「仅安装 / 未接入 / 不自动入库」。本批修正 10 个已接入工具的 reference 页（a_scan、dig、dnsx、ffuf、gowitness、httpx、katana、naabu、nuclei、wafw00f）、gowitness 的运行时页 chrome、`docs/OPERATIONS.md` 工具表 9 行、`docs/reference/README.md` 与 `docs/ACCEPTANCE.md` 的历史结论行；并借机把 Session 008 已完成的可信解析路径回写到 dig/dnsx 的接入状态与「待验证」。这不是纯文风改动：旧文字会让下一轮误判能力边界（HANDOFF 上一批就因此把已实现的 gowitness 范围约束当成待实现）。
- **4) 明确留待**：`frontend/src/data/dataset.ts` 的能力徽章仍按旧文档把 naabu/WSL httpx/gowitness 标为「未接入主流程」（`docs/audits/` 里的历史审阅报告也基于当时事实），需要单独一轮前端批次修改并重新构建、跑前端检查；`docs/audits/*` 属历史审阅记录，不追改；`docs/SOURCES.md` 里的是 Google DoH **JSON API**（与本次实现的 RFC 8484 线格式 DoH 不是同一入口），未混改。
- 验证：`ruff check --no-cache asm tests tools scripts` 全绿；新增 3 项 katana/范围测试 + 4 项文档矩阵测试全通过；完整非 WSL 回归见 `docs/ACCEPTANCE.md` 本批行。证据 `report/validation/web-surface-docs-unit.xml`。
- 边界：未改系统 DNS/代理/防火墙；未对任何真实目标发包（全部离线替身 + 127.0.0.1 回环夹具）；未开启真实 WSL 工具实跑（受限沙箱下子进程管道与浏览器启动被拒）；版本矩阵只记录既有事实，不把「已接入」等同于「已实网验收」。

## 2026-10-14 · Session 009 · WSL Web 工具范围控制：核实、加固与契约测试

- 用户指令「继续推进」。按 COVERAGE/HANDOFF 的下一优先级处理 Web 阶段 WSL 工具范围控制。**先以代码为准核实**：接力文档称 httpx/ffuf/katana/gowitness 已接入，而 HANDOFF 仍写「gowitness 浏览器子资源/导航的范围约束尚待实现」。读码结论是**约束已实现、HANDOFF 该句已过时**：katana 传 `-cs <精确 scope> -dr -duc`，gowitness 经 `--chrome-path chrome-wrapper.py`（`--no-sandbox` 仅在私有 user/netns）与 `--chrome-proxy <任务内代理>` 且 Chrome 只信任本任务代理证书的固定 SPKI，代理把每个 GET/HEAD 交回 Windows。
- 真正缺口因此是**可测性与证据**而非功能：范围判定原先内联在 `_http_job` 的帧循环里，无法单测，也没有任何测试证明「越界子资源零到达」这一 HANDOFF 自己提出的验收条件。本批把它提取为可测函数并补齐契约测试。
- `asm/external_tools.py`：新增 `crawl_scope(target)`（精确 `scheme://host:port` 正则，替换 `http_tool` 内联拼接，**行为不变**）、`BROKER_ARTIFACT` 常量（产物名白名单，替换 `_http_job` 内联 regex）、`broker_request(ctx, frame, requests, errors)`（把越界→403+scope_blocks、预算/授权类 `PolicyDenied` 必须上抛、方法/协议校验、body 编码统一到一处）。`_http_job` 与 `http_tool` 改为调用它们，语义与原先一致。
- `asm/workbench_tools.py`：`ExecutionContext.http()` 新增 `transport="target_http"` 关键字并透传给 `reserve_http_request`，broker 请求据此在物理账本中标记为 `isolated_http_broker`，与工作台自身的 `target_http` 请求可区分；默认值不变，既有调用与账本语义不受影响。
- 新增 `tests/unit/test_broker_scope.py` **32 项**（离线 + 回环夹具）：crawl-scope 精确性矩阵（近似域名 `.evil.invalid`、其它端口、其它协议、`127.0.0.10` 均不匹配）、GET/HEAD 转发参数（`follow_redirects=False`、`transport`、请求头、字节上限）与回执、越界 URL 得 403 且 `requests` 为空、预算耗尽与授权撤回必须 `raise`（不得伪装 4xx）、POST/DELETE/ftp/file 被拒且不调用 `ctx.http`、产物名白名单（拒绝 `screenshots/../evil.png`、`screenshots/sub/a.png`、`/etc/passwd`、`result.json.bak` 等路径穿越与后缀绕过）、跨主机 CONNECT 在询问协调器之前即 403（`seen == []`，证明没有发出 `http_request` 帧）、`scope_blocks` 进入 `tool_health` 回执。
- 其中 3 项用真实 `Workbench` + `m5_fixture` 回环 HTTP 夹具跑端到端：在范围 broker 请求确实到达夹具并被记入账本 `physical_request_started` 且 `transport=isolated_http_broker`；越界 `http://outside.invalid/lib.js` 得到 403、夹具零请求、账本零 `physical_request_*`（夹具同时把 `socket.getaddrinfo` 限制为 localhost，若发生解析会直接失败）；`max_requests_per_host=1` 时第二次 broker 请求触发 `http_request_budget_exhausted`，账本为 `started`+`blocked` 且夹具只收到一次请求。
- 验证：`ruff check --no-cache asm tests tools scripts` 全绿；新增 32 项与既有 `test_external_tools.py` 13 项合并 45 项全通过；完整非 WSL 回归见下条。证据 `report/validation/broker-scope-unit.xml`。
- 文档修正：`HANDOFF.md` 该条改为已核实+已测试，不再列为待实现；`docs/TOOL_INTEGRATION.md` 增补范围契约、明文 HTTP 与 HTTPS 隧道的刻意差别（HTTPS 按任务主机固定隧道；明文允许授权范围内其它主机但同样过范围/预算/回执）、以及本批专项验收；`docs/COVERAGE.md` web 行重写（该工具接入已完成、范围契约已测试，剩余改为 katana `-jc`/JSLuice 级 JS 端点、版本矩阵、CDN 现场差分、更广 HTTPS 浏览器路径）；`docs/ACCEPTANCE.md` 新增本批行。
- 边界与未做：未改系统 DNS/代理/防火墙；未对任何真实目标发包（全部为离线替身与 127.0.0.1 回环夹具）；未开启任何真实 WSL 工具实跑（受限沙箱下子进程管道/浏览器启动被拒），因此「更广 HTTPS 浏览器路径」与真实工具实跑仍属外部验收；capability 行为未改，仅提取函数 + 增加账本标记。

## 2026-10-14 · Session 008 · 可信 DNS 解析路径（DoH 加密上游 + 劫持答案隔离）

- 用户指令「推进任务」。按 HANDOFF/COVERAGE/本地接力 §10 的既定优先级，本批只做**第一优先级：建立可信 DNS 解析路径**；不改系统 DNS/代理/防火墙，不跑真实目标，不读凭据。
- 只读环境复测推翻了 Session 005 的部分结论并给出新的根因：本机**系统解析被劫持**——系统 DNS 服务器列表为 `10.10.10.1`、`202.114.0.131`、`202.114.0.242`、**`198.18.0.2`**（fake-IP 段），系统配置把 `example.com A/AAAA` 解析为 **`127.0.0.1` / `::1`**。而 Session 005 记录的"显式 1.1.1.1/114.114.114.114/8.8.8.8 的 UDP/TCP 53 返回 198.18.0.122"**本批未复现**：三家显式上游均返回真实地址（1.1.1.1、114.114.114.114 UDP/TCP 通过，8.8.8.8 TCP 通过、UDP 超时）。据实修正文档结论，不把旧观测当永久事实。加密侧：`223.5.5.5`、`1.12.12.12` 的 DoH 可用；`1.1.1.1`、`8.8.8.8` 的 DoH 在本机连接超时。
- 新 `asm/utils/dns.py`：`doh_endpoint()` 规范化并校验端点（必须 https、**主机必须是 IP 字面量**——否则要先解析域名，等于回到被污染的路径；拒绝账号密码/query/fragment；端口 1–65535）；`doh_query()` 用 dnspython 组包、base64url `GET ?dns=`、`accept: application/dns-message`，`trust_env=False`、`follow_redirects=False`、响应上限 64 KiB、校验 content-type、**校验 question 回显**、只取 CNAME 链可达的同类型答案并有条数上限，rcode/截断/HTTP 错误分别归类；`record_value(..., reject_loopback=)` 新增公网回环地址拒绝；`DNSSettings` 新增 `doh_resolvers`/`doh_trusted`。该模块同时作为 WSL `dns_support` 被 stdlib-only 的 dig worker 导入，因此 `httpx` 只在函数内延迟导入，模块级保持标准库。
- `asm/stages/s5_dns_cdn.py`：新增 `collect_doh()` 与 live 分支接线；加密端点作为独立来源 `doh` 进入既有来源/上游证据体系；来源优先级加入 `doh`；当配置了 `doh_resolvers`（且 `doh_trusted`，默认 true）时，**加密 A/AAAA 成为交给 Stage 6 与报告的 selected**，并新增 `doh_verification`（resolvers/trusted/compared/differences/selected_from/status）；加密与明文都可用且不一致时产生 `dns_doh_mismatch` finding + partial；加密无可用结果自动回退明文，不因 DoH 失败丢掉整段解析。公网目标收到回环答案时记录 `dns_loopback_answer` 并拒绝（`target_local` 本地靶场显式豁免），避免被劫持的解析把扫描打到本机。
- `asm/stages/s4_subdomain.py`：`resolve()` 不再使用 `dns.resolver.Resolver()` 的**系统配置**（那正是被劫持的来源），改为 `configure=False` + 显式上游，默认回退到固定公共上游而非本机列表；原闭包重构为可测试的模块级 `trusted_resolver()`，并在此处同时拒绝 fake-IP 与回环地址——被劫持的上游无法凭空制造子域。`asm/conf.py`：仅当显式配置了 `doh_resolvers` 才把它写入有效 DNS 配置，未配置的 profile 保持原有键集合与恢复指纹不变（新增测试断言该性质）。`asm/policy.py`：`dns_keys` 增加两个映射，使 DoH 设置进入计划参数与预览。
- 新增 `tests/unit/test_doh_dns.py` **24 项**：端点校验矩阵、配置校验与去重、wire 格式与 accept 头、五种记录类型、NXDOMAIN/SERVFAIL/HTTP 503、超时、content-type 不符、超大响应、截断、question 不匹配、无关/不支持答案、客户端硬化（`follow_redirects`/`trust_env`/`timeout` 实际取值）、Stage 5 加密优先于被投毒明文、路径冲突证据与 finding、加密失败回退、未配置时行为不变、公网回环拒绝与 target_local 豁免、`collect_doh` 覆盖全部域名×类型、Stage 4 不继承系统配置、被劫持上游无法制造子域、配置指纹可选性与策略参数流转。全部离线（`httpx.MockTransport`），无真实解析或目标请求。
- 验证：`ruff check --no-cache asm tests tools` 全绿；新增 24 项全通过；完整非 WSL 回归 **344 passed / 4 failed**。4 项失败均为**受限沙箱环境阻塞**且与 DNS 改动无关：MSYS `openssl` 生成夹具证书时 `couldn't create signal pipe, Win32 error 5`（1 项）、Playwright 启动浏览器 transport 时 `PermissionError(13)`（2 项截图 + 1 项集成截图）。失败原样保留，不计入通过；未做 stash 对照（见下条沙箱限制）。
- 本机实测证据 `scripts/dns_trusted_path_evidence.py` → `report/validation/dns-trusted-path-20261014.json`（**只查询公共示例域 `example.com`，不涉及任何调查目标**，Stage 5 摄取全程在内存库中）：系统解析 `A 127.0.0.1 / AAAA ::1`；显式明文与两个 DoH 端点均给出真实地址；配置 DoH 后 `selected_from=doh`、`trusted=true`，selected 为真实地址（104.20.23.154/172.66.147.243 与两个 IPv6）；仅喂系统解析结果时 selected 为空、两条回环答案被拒并产生 `dns_loopback_answer`。
- 沙箱事实（影响本批记录方式，非仓库缺陷）：本会话 `pwsh` 子进程运行在 **Low 完整性级别**，而工作区内既有对象是 Medium 标签，因此**命令行写不进** `.git`、`asm/`、`tests/`、`data/validation/` 等既有目录（DACL 实际允许 `Authenticated Users (M)`，被阻断的是完整性级别，属预期沙箱约束，故未改权限）；由沙箱进程新建的路径（如 `report/validation/`）可写，本批证据与 JUnit 因此落在 `report/validation/`。**因而 `git commit`/`push` 未执行**（无法创建 `.git/index.lock`），文件改动由编辑器工具完成，待用户决定是否授权一次提权提交。
- 文档同步：`docs/RUNBOOK.md`（DoH 配置块与语义）、`docs/OPERATIONS.md` 第 8 节（重写解析路径现状、修正 Session 005 结论、记录已实施路径与实测）、`docs/COVERAGE.md`（DNS 行与历史段落修正）、`docs/ACCEPTANCE.md`（新增可信路径与本批验证行、修正公网 DNS 行）、`HANDOFF.md`（接力段与本批结论）、`README.md`。
- 未做/边界：未修改系统 DNS/代理/网络/防火墙；未查询任何真实目标或凭据；未把 DoH 写入任何仓库内 profile（开启会改变解析来源与恢复指纹，且属实网行为）；六个调研工具与 WSL Web 工具接入仍按原优先级待在 DoH 之后。自有域名实网核对需用户提供授权与凭据。

## 2026-10-12 · 已有工具流程接入与原 WSL 核对

- 用户范围：先完成已有工具，Amass/gau/waybackurls/LinkFinder/arjun/x8下一批。工具清单在tools/README.md，完整流程与验收在docs/TOOL_INTEGRATION.md。
- 已有搜索引擎/被动来源继续独立步骤；新增OneForAll隔离live job、dnsx/dig、naabu/a_scan、httpx/ffuf/katana/gowitness/nuclei/wafw00f、SecLists冻结输入。多工具独立入队、tool_options参数、反馈、证据及双版报告沿用共享引擎。
- 错误处置记录：受限进程WSL列表为空，被误判为本机没有WSL，新增独立Ubuntu-24.04并开始部署。正式权限核实原Ubuntu仍为默认发行版，用户longchuanli、/home/longchuanli/asm-ws及原工具/字典均在。已停止新增部署进程并终止Ubuntu-24.04；未注销任何发行版、未迁移原数据，后续直接复用Ubuntu。
- Bridge、CLI、依赖检查、.env.example和脚本默认名称统一Ubuntu；显式环境配置优先，实际.env未读写。准备脚本只接受已存在发行版，空/不可见列表报错，永不自动安装或注销WSL；新增回归保护这一行为。a_scan任务副本部署到新results目录，原脚本哈希保持一致。
- 原Ubuntu真实回环：native-tools-live-20261012-150726五项dig/dnsx、naabu/a_scan/Nmap均观察到夹具；external-tools-live-20261012-150458的httpx/ffuf/katana/wafw00f/nuclei通过。gowitness早期退出0却无PNG的误判已修复；gorod最终实跑external-tools-live-20261012-151602生成1280×720 PNG并视觉核对、进入双报告。chromedp本机隔离环境超时，默认使用gorod。自有验收进程/夹具均已结束。
- 全单元回归317通过（tool-integration-unit-all-20261012.xml），最终相关回归90通过（original-wsl-final-20261012.xml），变更Python文件Ruff及前端构建通过。全仓Ruff另有既有frontend审查脚本的11项问题，未改动无关用户文件。此前失败证据保留，不冒充真实工具执行。
- 未查询真实账户/目标，未读取秘密，未提交/推送。OneForAll新live job/公开提供商、Masscan实际网络接口及Nmap服务/UDP/NSE等外部验收仍单独待补，已安装与回环通过不等于这些项已验收。

### 收尾 · 复跑与推送

- 提交前复跑完整单元回归：**320 passed**（原 317 + 3 项新增 WSL 运行时守卫测试），JUnit 0 failures/errors/skipped，证据 `data/validation/tool-integration-unit-20261012-recheck.xml`。受限沙箱内同命令有 3 项失败，全部因命名管道被拒（openssl 生成测试证书、asyncio 子进程管道），属会话沙箱限制而非代码缺陷；放宽权限后同命令全绿。新增的 3 项即上文守卫：空/不可见发行版列表不得自动创建 WSL、默认复用 Ubuntu、gowitness 无图退出 0 不算截图完成。
- `ruff check asm scripts tests tools` 全绿：5 个既有前端探针脚本原有 11 项问题清零，仅删未使用导入/未使用局部变量、消除歧义变量名（`l`→`lbl`），无行为变更，脚本语法另行复检通过。前端 `tsc -b && vite build` 复跑通过，仅保留既有 chunk 体积告警。这两步都要求真实子进程管道，受限模式下被拒。
- 提交 `eeddb0977b21f7514fd035001bd59c63d37b1409`（192 个文件，含工作台前端、审计文档与验收脚本）已推送 main，`git rev-parse HEAD` 与 `git ls-remote origin refs/heads/main` 一致。首次推送因远端连接重置失败，重试后成功。
- 暂存前断言未包含真实目标与本地数据：`待测域名.txt`、`report/`、`*.local.ts`、`.env`、`PUSH_RECEIPT.local.json` 均未进入提交；`.gitignore` 增加本机待测域名清单规则（真实目标，只能本地保留）。未提交任何凭据。
- 四环境 CI [38563972959](https://github.com/decline-llc/asm/actions/runs/38563972959)：只有 `ubuntu-latest` + Python 3.12 的 pytest 步骤失败，同一任务的 ruff 通过；3.11 同构任务通过，Windows 两项因 fail-fast 取消。GitHub 的 job/run 日志下载对匿名访问返回 403（需仓库写权限），因此先补充**匿名可读的失败注解**再复跑定位：新增 `scripts/ci_report_failures.py`（把 JUnit 失败用例名与首行原因输出为 `::error::` 工作流命令，本地运行加 `[local]` 前缀，始终返回 0）与 CI 中 `if: failure()` 的注解步骤。
- 本机复核未复现同一原因：Windows Python 3.11 下 320 项单元与 324 项 CI 同构套件全部通过；WSL Ubuntu 3.12.3 复跑（同一 CI 选择器）只出现 2 项浏览器用例失败，原因是该 WSL 未安装 Playwright 浏览器（截图无产物、无请求），属复现环境差异，不作为 CI 同因证据。已终止 WSL 的 Chromium 下载。
- 本轮未重跑外部工具与真实提供商，原有回环证据保持有效；CI 复跑结论随后追加。
- 复跑 [38568884230](https://github.com/decline-llc/asm/actions/runs/38568884230) 又失败，但这次**注解直接给出证据**：失败任务是 `windows-latest` + Python 3.12，10 项失败中 9 项是 `tests/unit/test_dns_workers.py` 的 `PermissionError: [WinError 10013]`（套接字绑定被系统保留端口范围拒绝），另 1 项是并发用例的 `assert 1 == 2`（负载下的时序抖动）。两个 ubuntu 任务全部通过，Windows 3.11 被 fail-fast 取消，因此**首次 run 38563972959 的 ubuntu 3.12 失败至今未复现**，只能据实记为未复现（本机 320/324 全绿、同一提交第二次运行的 ubuntu 3.12 全绿）。
- 根因定位：本机历史报告 `dns-workers-fixed.xml` 含同类 10013，新脚本把它定位到 `tests/fixtures/dns_server.py` 的夹具绑定行；且 `test_missing_permission_sends_no_dns_packet` 除创建夹具外不做任何套接字操作，可排除客户端侧。原夹具只对 TCP 绑定重试 16 次、UDP 绑定异常直接抛出，且每次都依赖端口 0 的连续分配，在保留端口密集的 Windows 上会连续落入同一批被拒端口。
- 修复：`tests/fixtures/dns_server.py` 改为对 UDP/TCP 绑定一起重试，候选端口先取 0 再随机展开（20000–59999，48 次），并把可重试错误码同时按 `errno` 与 `winerror` 判定；`tests/unit/test_dns_workers.py` 并发用例的服务端延时 0.2s→0.5s（断言不变）以稳定重叠窗口。本机 43 项 DNS 相关用例通过（唯一失败仍是沙箱命名管道限制下的 openssl 证书夹具，放宽权限后通过）。
- 复跑 [38572523201](https://github.com/decline-llc/asm/actions/runs/38572523201)：`WinError 10013` 全部消失（夹具修复生效，9 项失败清零），只剩 1 项 `test_configured_workers_make_real_concurrent_local_queries[dns_enum]` 的 `assert 'partial' == 'completed'`：负载下某次 DNS 查询超过 2s 客户端超时被判 `LifetimeTimeout`，步骤随之失败、run 变 partial。修复：该用例 DNS 参数 `timeout_seconds` 2→5（共享校验上限 30，断言不变）；同时让 CI 注解把最深层栈帧写进消息正文（GitHub 会忽略工作流命令的 file=/line= 属性），并把 `file=`/`line=` 保留为属性。本机 15 项 DNS worker 用例通过。
- 最终代码提交 `d3f33ecb23886982d3ec44b8b77ca3949cddbebf` 的四环境 CI [38575650738](https://github.com/decline-llc/asm/actions/runs/38575650738) **4/4 jobs success**：Ubuntu/Windows × Python 3.11/3.12 的 ruff、非 WSL pytest、sdist/wheel 构建全部通过（Windows 两个任务 13:53→14:00）。此前两次失败都是 Windows 运行器环境敏感性（保留端口范围触发 10013、负载下 2s 超时），已修复并在 CI 复验；**首次 run 38563972959 的 ubuntu 3.12 失败仍未复现**，据实保留为未复现。本批提交链：`eeddb09`（本批功能）→ `cc97a1e`（CI 失败注解）→ `7a621a9`（DNS 夹具端口）→ `d3f33ec`（DNS 超时余量），其后仅文档同步，按 `paths-ignore` 不触发 CI。最终代码上本机复跑 CI 同构选择器 **324 passed / 9 deselected in 257.41s**（`report/validation/unit-after-fixture-fix.xml`，本地文件不入库）。

## 2026-10-11 · 项目分类与历史证据页面整理

- 按用户澄清将业务调查与开发验收分开。18 份本机配置迁入 `profiles/investigations/`（2 份）及 `profiles/validation/`（16 份）；原数据库 15 个项目均为验收记录，在默认业务列表隐藏，测试入口保留。新配置与新交付按用途分目录，后续验收数据库独立于业务库。CLI 短配置名和 API 导入兼容分类路径。
- 迁移前备份数据库并保存清单，迁移后验证 18 份配置内容哈希及运行/步骤/事件/资产/证据/receipt 等表的内容哈希一致。原始报告、证据包、路径引用、权限修订保持。备份与清单位于 `data/organization/20261011_120716_724684/`。
- 项目中心提供卡片/列表/表格、搜索与排序；原顶部新建调查跳转问题已修复。历史证据 `?pilot=1` 脱离演示项目上下文，使用实际调查主体，提供候选/DNS/范围外/子域/台账分区、来源筛选、全文搜索、排序、分页、列表/表格、详情与原始记录、CSV 和原 HTML 导出。
- 验证：26 项项目分类/API/运行/交付/证据包针对性测试通过，前端类型检查与生产构建通过，ruff 与 diff 检查通过。浏览器验证分类、三视图、迁移后历史运行打开、搜索/详情/分页/台账、8 行 7 列 CSV 与包含 2 张内嵌 PNG 的 HTML；浏览器无错误。截图和结果在 `data/qa/project-organization/`。6100 前端及 6400 后端已加载本次改动。

## 2026-10-09 · Session 001 · 启动与环境盘点

- 输入：根目录 v2.0 工程设计、`asm_full_design_v2.html`、`deploy_topology_v2.html`；原始文件保留不改。
- 初始状态：无源码、无 Python 项目配置、无 Git 仓库。
- 用户要求：工具统一在 WSL；目录分类和 README；每次实施留记录，随时可由下一位 AI 接力；优先可用的 GitHub 方案。
- GitHub 连接器可读到已登录账号 `decline-llc`，两次仓库枚举返回空列表，当前未发现可写目标仓库，连接器没有建仓工具。尚未上传任何文件。
- 执行环境异常：工具参数指定 `pwsh.exe`（含绝对路径）后，实际版本仍是 Desktop 5.1。确认后停止用该宿主执行项目命令。
- PATH 发现 PowerShell 7.6.6 Store 安装，但直接启动返回“拒绝访问”；旧的 7.6.1/7.6.2 路径已不存在。
- `wsl.exe --list --verbose` 返回 `Wsl/EnumerateDistros/Service/E_ACCESSDENIED`。没有改动发行版或在 Windows 安装扫描工具。
- 后续：在权限允许的文件工具中构建代码与文档；真实 WSL 验收与 PowerShell 执行必须准确标记状态，不能把模拟测试写成实网通过。

本文件持续追加。每个批次记录变更、验证命令与结果、未完成项；最终状态以 `HANDOFF.md` 和 `docs/ACCEPTANCE.md` 为准。

## 2026-10-09 · Session 002 · 恢复执行与继续构建

- 从同目录前一轮聊天和本地文档恢复目标；用户已授权继续实施、WSL 工具安装和 GitHub 交付。
- 沙箱执行助手仍报 `helper_unknown_error: setup refresh had errors`；通过正式提权通道恢复命令执行，实测 PowerShell 为 `Core 7.6.5`。
- WSL 现可列出已有 `Ubuntu` 发行版，WSL2，初始状态 Stopped；原 Session 001 的拒绝访问属于历史状态。
- GitHub `decline-llc/asm` 当前仍为空，仓库元数据显示 push 权限；连接器实际写入尚未复验，不把元数据视为提交成功。
- 现存文件仅有配置、模型、范围/精度规则骨架。继续补齐桥接、数据库、阶段、面板、CLI、工具部署、离线/本地验收和目录 README。

### 批次 1 · 核心实现与初次验证

- 新增 db/bridge/pipeline/CLI/doctor、全部阶段入口、六引擎响应适配器、股权 fixtures 状态机、OSINT SSE 与公告解析、供应链线索、八 sheet 报告。
- 本机 `.venv` 使用现有 Windows Python 3.11.9，已安装 dev/browser 依赖及 Playwright Chromium。
- WSL 为既有 Ubuntu 24.04.4 LTS，保持代码 Windows / 二进制 WSL 架构；与设计指定 22.04 的发行版差异明确保留。Ubuntu 24.04 Python 工具使用各自 venv。
- 八个固定版本二进制已下载并验证官方 release SHA-256；工具清单 `tools/tool-lock.json`。Chrome 安装遇到 unattended-upgrades 占锁；增加 apt 等锁选项。自动更新随后留下 dpkg 中断状态，执行 `dpkg --configure -a` 与 uuid-runtime 重装后恢复；未停止系统自动更新服务。
- 离线首轮 11 项单测通过。完整首轮：20 passed / 2 failed；失败均为真实 WSL 后台任务未产生 done。开始改用异步保留 Windows WSL 客户端会话，Linux 侧仍用 timeout 与完成标记，避免最后一个客户端退出后任务被回收。
- 演示 `demo --dry-run --passive-only` 各阶段完成；再次 `--resume` 全部跳过。演示数据库隔离在 `data/demo/dry-run/`。
- 2026-10-09 用户再次明确要求推送 `decline-llc/asm` 并及时记录 docs。已初始化本地 main 和 origin；远端读取仍为空，尚未推送。提交身份使用用户 GitHub login 及该账号公开 noreply 地址。

### 批次 2 · WSL 实测修复与交付文档

- 根因：最后一个 Windows WSL 客户端退出后，当前 WSL 环境会回收后台会话。改为每任务 `subprocess.Popen` 保留客户端，后台不阻塞 Python 调度；工具 timeout、原始日志与 done/rc 仍保留在原生 WSL。
- 修复后真实 WSL 测试 2 passed（7.50s）：完成/失败均回收、256 字节二进制 tar 保真、root nmap 发现 3 TCP + 1 UDP 回环端口。
- 增加 CLI 本地演示、UDP 配置支持、GitHub Actions（Windows/Linux × Python 3.11/3.12）、各目录 README、RUNBOOK/COVERAGE/SOURCES/ACCEPTANCE。
- 核心代码并未覆盖设计全部方法；COVERAGE 列出实际缺口，拒绝把骨架或 fixtures 当成完整实网验收。

### 批次 3 · 最终基础版验证与推送准备

- 完整测试重跑：`ASM_TEST_WSL=1 python -m pytest -q --junitxml=data/validation/pytest.xml` → **22 passed in 24.66s**，无 skip。
- `ruff check`、`pip check` 全绿；`python -m build` 成功产出 sdist + wheel（运行仍按仓库 editable 模式）。
- `scripts/local-demo.py` CLI 实跑完成阶段 1/3/5/6/7/8：assets=4，TCP 8765/8766/8768，UDP 8767，URLs=14，Web 注入路由=13，quarantine=0。
- Playwright 截图和 xlsx 相对链接有效；Artifact Tool 只读渲染全部 8 张 sheet，已检查总表/URLs/todos，继续核验其余。截图与渲染结果不提交仓库。
- WSL 直连 HTTP Ubuntu 源受到本机代理 fake-IP 影响，HTTPS 官方源可达；安装脚本改用项目临时 HTTPS source list，不改 /etc 系统源。已继续安装 Chrome、wafw00f、OneForAll/SecLists。
- `git check-ignore` 确认 .env、data/test/asm.db、.venv 被忽略。准备首次 main 提交和推送，提交/远端证据随后追加。

### 批次 4 · 首次推送与部署复验

- 统一文本 LF，清除 SSE fixture 末尾空行；`git diff --cached --check` 通过。首个提交 `49044d19945012a97103ca48ce0a504feca4cd7d`，86 个文件。
- 首次 Git push 因多账号未选定、禁止交互时无法获取 Username 而失败；GitHub 连接器写 blob 仍返回 403 `Resource not accessible by integration`。本机 GCM 已有 decline-llc 凭据，配置仓库级 `credential.https://github.com.username=decline-llc` 后成功 `git push -u origin main`。未读取、输出或写入明文令牌。
- `git rev-parse HEAD` 与 `git ls-remote origin refs/heads/main` 均为上述 SHA，已验证远端提交。GitHub Actions 首轮 [37918864553](https://github.com/decline-llc/asm/actions/runs/37918864553) 四环境（Windows/Linux × Python 3.11/3.12）全部通过。
- 八张报表已全部只读渲染并逐页检查，视觉核验通过。运行数据、浏览器截图与渲染结果保持本地。
- `doctor` 首轮 15/18：发现直接 WSL 命令 PATH 引号、UTF-16LE Windows 警告与 Linux UTF-8 混合解码、Windows 管道编码，以及 Python 3.12 OneForAll 缺少 distutils shim。已修复对应代码并给 OneForAll 增加固定 setuptools 75.8.0 依赖；回归验证继续中。
- Chrome、wafw00f 与 OneForAll requirements 安装完成；SecLists 2026.1 原生 WSL clone 持续下载。17/18 等临时状态不可当作环境就绪，最终以 18/18 实测结果为准。
- 后续复验发现 OneForAll exrex 0.10.5 使用 Python 3.11+ 已移除的 re.sre_parse，固定覆盖为 0.12.0；导入已通过。工具目录所有权交回 WSL 普通用户。
- 快速 nmap 任务在 done 检查后、client poll 前完成，导致误判失败。现在 client 退出时重新检查 done，并加入确定性竞态测试；完整测试 **24 passed in 24.87s**，ruff 和 sdist/wheel 构建通过。
- GitHub 官方固定 commit 递归 tree 显示 SecLists 共 6412 项、文件总量 1,964,874,086 bytes，超出原设计约 500MB 估计。改为固定版本 partial clone + 所需字典 sparse checkout，完整版本仍可显式安装。中断本次 full clone 时，Git 自身清理临时下载目录；预定保留操作未成功，未涉及用户源码或其它字典。

### 批次 5 · 环境最终验收与追加交付

- 修复与记录已提交 `fad93706bd240a60738839788e1f4bc1e506cd06` 并推送 main，本地/远端 SHA 一致；四环境 CI [37921283447](https://github.com/decline-llc/asm/actions/runs/37921283447) 已触发。
- 重复安装时 root 读取普通用户持有的第三方 Git clone 触发 dubious ownership。安装器只为具体源码目录设置本次命令的 safe.directory，不写全局例外；Windows bootstrap 验证并显式传递 0/1 部署选项。
- SecLists 元数据成功，但 Git lazy-fetch 第二连接超时。改用官方 raw 固定 commit 下载所需七个文件，逐一比对 Git tree blob SHA 并写入 object store；全部校验通过，完成 sparse checkout（本地约 2.7MB）。原版完整字典未自动下载。
- OneForAll 生成有效 requirements，避免重复安装时先降级再升级 exrex；保留源码原文件。masscan 1.3.2 的 --version 退出码为 1，清单步骤只接受该已验证特殊码，避免安装成功被版本记录误判失败。
- 本次 `init-wsl` **exit 0**，生成原生 WSL `manifests/installed.txt`；Chrome 155.0.8059.39、wafw00f 2.4.2、八固定二进制与两源码 commit 已记录。
- 最终 `asm doctor --json-output` **exit 0，18/18 全部通过**，证据 `data/validation/doctor.json`；包含 OneForAll 普通用户导入、字典存在、根权限、Chromium 与磁盘/桥接延迟。
- 已验证显式 GBK 管道下 CLI 输出可解析 UTF-8 JSON；`pip check` 与 `git diff --check` 通过。八报表视觉核验、24 项本地完整测试和构建证据保持有效。
- CI 已配置只改文档时跳过重复运行；代码或配置变更仍验证 Windows/Linux × Python 3.11/3.12。完整设计缺口、DNS fake-IP 与待实网输入保持明示，未宣称 v2.0 DoD 全项完成。

### 批次 6 · 远端最终核验

- 最终代码提交 `a3625450bb67fe9c44f318bb0732814c5476918e` 已推送 main；`git rev-parse HEAD` 与 `git ls-remote origin refs/heads/main` 完全一致。
- [最终 CI 37921900265](https://github.com/decline-llc/asm/actions/runs/37921900265) 四个 job 全部 success：Ubuntu/Windows × Python 3.11/3.12，均完成依赖与浏览器安装、ruff、非 WSL 测试和构建。前两轮 CI 亦通过。
- GitHub 固定代码 commit 的 docs/ACCEPTANCE.md 已可直接读取，含 24 passed、18/18 及完整设计缺口说明，确认记录已进入远端。
- 本地 JUnit 最终 24 tests、0 failures、0 errors、0 skipped；doctor 18 项全绿；敏感 .env、数据库、报表、截图均被忽略。
- 本次收尾仅更新文档；最终文档提交推送后，再核对 main SHA 与工作区，实际最终 SHA/时间保存到被忽略的 `docs/PUSH_RECEIPT.local.json`，避免在提交正文中自引用自身 SHA。

## 2026-10-10 · Session 003 · DNS/CDN 下一批实施

- 从 eba0ee9 干净 main 恢复接力；既有推送与持续记录授权继续有效。
- 沙箱助手启动仍失败，正式提权通道可用；Windows 命令继续显式使用 PowerShell Core 7.6.5。
- 本批优先实现 WSL dnsx/dig、三解析商对比与国内修正、Windows 显式上游复核、CNAME 链、无效/fake-IP 隔离，以及向端口阶段传递选择后的地址。
- 参数依据本机 dnsx 1.3.1 帮助与官方 dnsx/dnspython 文档；外部工具 I/O 继续只走原生 WSL，通过 stdin/tar 交换。
- 验收只使用脱敏 DNS 数据和本地回环 DNS 服务器，不依赖未提供的实网域名/API credentials。

### 批次 1 · 显式上游与证据衔接

- 新增 DNS 参数校验与生效默认值；有效设置纳入 profile fingerprint，旧 profile 也不会复用原系统 DNS 阶段状态。
- 原生 WSL stdlib dig 包装器查询 A/AAAA/MX/NS/CNAME，并追踪链终点、环路、上限、NXDOMAIN 和错误；dnsx 按各配置上游独立异步运行。Windows dnspython 使用 configure=False 复核指定上游。Stage 4 字典使用优先上游。
- 保留按 source@resolver 的可用记录、过滤前观测和差异事实；同一上游按 dig → Windows → dnsx 选择成功观测，不将复核分歧合并为扫描地址。优先国内上游有可用 A/AAAA 时采用它，拒绝 unspecified/fake-IP；Stage 6 和域名报告使用 selected。
- CNAME 外部链节点不扩大范围；默认不 HTTP 探测。主动授权且开启 takeover_probe 才请求原始域名，匹配 provider/status/error 文本后生成 review 证据；保存匹配文本与响应摘要，未执行注册或接管。
- 修复恰好 max_cname_hops 时终点无 CNAME 被误标 max_hops 的边界；支持合法 null MX `0 .`；nmap IPv6 目标携带 -6（原生 IPv6 主动扫描仍待验收）。

### 批次 2 · 回归与交付准备

- 聚焦 DNS + 真实 WSL 验证：12 passed in 24.89s。三组 WSL 回环 DNS 服务真实 dnsx/dig 输出均已解析，国内/选定地址 192.0.2.20；0.0.0.0 和 198.18.0.8 留作拒绝证据，不进入可用记录。Windows 指定上游 A/AAAA/NXDOMAIN/超时独立通过。
- 完整 `ASM_TEST_WSL=1 python -m pytest -q --junitxml=data/validation/pytest.xml`：**35 passed in 44.72s**，JUnit 0 failures / 0 errors / 0 skipped；包括 CNAME 环路/上限/恰好上限/悬空/超时、来源分歧不污染地址和报告旧记录不回退。
- `ruff check asm scripts tests tools`、`pip check` 全绿，sdist/wheel 构建成功；CI 扩大静态检查至整个 tools 目录。未改工具安装，既有 18/18 doctor 环境证据保持有效。
- 本批 `scripts/local-demo.py` exit 0，阶段 1/3/5/6/7/8 完成：3 TCP（8765/8766/8768）+ 1 UDP（8767）、4 assets、14 URLs、13 Web routes、0 quarantine；DNS → 端口 → Web → 报告链路保持有效，证据 data/validation/local-demo.json。
- 脱敏实际 DNS 输出复制到被忽略的 data/validation/dns/multi-resolver/ 与 negative-cases/；.env、venv、验证数据和本地 push receipt 均确认不提交。
- 推送前核对远端 main 仍为 eba0ee9，与当前基础 HEAD 一致。更新 README/HANDOFF/COVERAGE/ACCEPTANCE/RUNBOOK/SOURCES 及工具/测试说明；本批公网 DNS/CDN、HTTP 接管和 IPv6 端口验收的边界保持明确。

### 批次 3 · 推送与远端验收

- 代码与记录提交 `ded0c15883f2ac34c9a9d51dfe2ae242cb0e9518`，22 个文件；`git diff --cached --check` 通过，未包含运行数据或凭据。
- 已成功 `git push origin main`；`git rev-parse HEAD` 与 `git ls-remote origin refs/heads/main` SHA 完全一致，推送后工作区干净。
- 四环境 CI [38015713303](https://github.com/decline-llc/asm/actions/runs/38015713303) 已触发，正在核对 Windows/Ubuntu × Python 3.11/3.12 的结果；最终结论随后追加。
- 收尾核对发现 HTTP 指纹候选只写 takeovers 表，报告 todos 未包含它。追加 takeover_candidate finding，让 provider、终点、URL、状态、匹配文本、响应摘要和 review 状态进入报告；扩展既有指纹测试验证实际 xlsx 待办出口。
- 追加修复验证：`ruff check asm scripts tests tools` 全绿；DNS/报告定向回归 **11 passed in 2.68s**，证据 data/validation/dns-report.xml。WSL 查询/端口部分未改，完整 35 项证据继续有效；最新代码将再次验证四环境 CI。
- 追加代码 `385c02d196076f3f0205780a25c92fc1766ab878` 已推送 main，本地/远端 SHA 一致。最新四环境 CI [38015955639](https://github.com/decline-llc/asm/actions/runs/38015955639) 已触发；以这一提交的结果作为最终代码验收。
- 等待远端期间只读核对 OneForAll v0.4.5 原生 CLI help，exit 0；brute/dns/req 默认开启，下一批接入须显式关闭并让 Stage 5 统一处理解析，参数与未完成状态记入 HANDOFF。未运行公网扫描。
- 最终代码 CI [38015955639](https://github.com/decline-llc/asm/actions/runs/38015955639) **4/4 success**，run head 为 385c02d196076f3f0205780a25c92fc1766ab878；Windows/Ubuntu × Python 3.11/3.12 全部完成浏览器安装、ruff、31 非 WSL 测试（4 WSL deselected）及 sdist/wheel 构建。四项 WSL 验收另在本机完整 35 项测试中通过。
- 本次最终提交仅同步 ACCEPTANCE/WORKLOG/HANDOFF，不重跑已通过的代码 CI；推送后对照 main SHA 和工作区，实际最终文档 SHA/UTC 时间保存到被忽略的 docs/PUSH_RECEIPT.local.json，避免正文自引用提交 SHA。

## 2026-10-10 · Session 004 · OneForAll 调度接入

- 从 1e8267f 干净 main 继续；执行仍显式使用 PowerShell Core 7.6.5 和正式提权通道。
- 核对原生 WSL 固定 commit 源码，发现关闭 brute/dns/req 仍会触发 wildcard/SRV；check.cdx 是 crossdomain.xml 主动访问，并非 archive CDX。包装器直接调用被动 Collect 与原生数据库/导出步骤，精确保留授权 root，不采用主流程的注册域扩张。
- 支持七个核验过的公开被动来源，默认五个，避免与既有 crt.sh/HackerTarget 重复；排除目标站点/DNS检查及付费 API 模块。按来源限定 HTTP 主机、关闭自动重定向、限制响应和超时，每任务数据库、临时文件与日志独立，不修改第三方源码。
- 原生去重只保留首个来源；因此先导出去重前观测，再保留原生 JSON 输出。Windows 仅合并白名单域名及 oneforall:来源，不直接导入工具 IP/端口字段，交由 Stage 5 统一解析。
- 验证将覆盖真实 WSL/vendor 的离线响应流程、来源合并、被动隔离、失败/超时和幂等；公网服务与已知子域覆盖率仍待自有目标输入。

### 批次 1 · 真实工具采集与边界验证

- 增加真实 WSL 离线 transport 夹具，运行实际七个采集模块、Module、SQLite 和 JSON 导出；阻断所有 socket connect/getaddrinfo，确认无隐藏 wildcard/SRV、目标 HTTP 或外部网络请求。第三方源码保持原样。
- 首轮真实工具测试 4 passed / 1 failed：上游模糊提取还保留输入 root，测试预期误少算七条来源；纠正期望并保留全局/root 双重范围过滤。未将范围外域名加入资产。
- 核对 AlienVault 发现第二次赋值覆盖第一端点结果；进程内合并子域集合，夹具使用两个端点各有一个独有子域，确认都进入导出与来源观测。超时线程明确标 timed_out，避免仅日志报警但任务误成功。
- 定向 `pytest tests/unit/test_oneforall.py tests/integration/test_wsl.py -k oneforall`：**12 passed in 27.49s**（其余 4 个 WSL 测试 deselected）。覆盖 Stage 4 后台调度及来源合并、离线模式不启动工具、七来源、独立 root 数据库、成功复用、空结果、HTTP 部分失败、模块/任务超时和失败重试。
- 新增 requests 作为 dev 测试依赖；生产 WSL 使用其已固定的独立 vendor venv。ruff 全绿；完整回归、依赖检查和构建进行中。

### 批次 2 · 完整回归与推送准备

- 完整 `ASM_TEST_WSL=1 python -m pytest -q --junitxml=data/validation/pytest.xml`：**47 passed in 64.58s**，零失败/错误/跳过，包含 9 个真实 WSL 测试。ruff、pip check 全绿，sdist/wheel 构建成功。
- 更新 README、HANDOFF、COVERAGE、ACCEPTANCE、RUNBOOK、SOURCES 及工具/测试/夹具说明，明确真实 vendor 核心离线验收与公网提供商可达性/覆盖率的区别。后续优先 WSL Web 工具接入。
- JUnit 核对 47 tests / 0 failures / 0 errors / 0 skipped。九个实际 OneForAll 任务（含两 root 与失败重试）的原始文件复制至被忽略的 data/validation/oneforall/，index.json 汇总 rc/状态；全部 network_attempts=0。原生第三方 `git diff --exit-code HEAD --` 为 0，源码无修改。
- 推送前远端 main 仍为基础 1e8267f；git diff --check 通过，.env、全部验证数据与本地 push receipt 被忽略。本批代码提交与四环境 CI 的实际结果随后追加。

### 批次 3 · 推送与远端验收

- 已提交 `019f6e472faa16f5dd5ee2ca0b84f1b9d1e7fe37`（20 个文件）并成功推送 main；本地 HEAD 与远端 refs/heads/main 一致，推送后工作区干净。
- 最新四环境 CI [38018126858](https://github.com/decline-llc/asm/actions/runs/38018126858) 已触发，head 为上述代码提交；Ubuntu 两项已 success，Windows 两项仍在浏览器安装，最终结论随后追加。
- 等待期间只读核对已部署 httpx/ffuf/katana/gowitness 帮助，均 exit 0，文本保存 data/validation/web-tool-help/。httpx 有 JSONL、显式 resolver/IP allow 和关闭更新检查；ffuf 默认不跟随跳转且可限制 rate；katana 默认 rdn 范围并跟随跳转，下一批必须显式设置 scope、disable-redirects 和 disable-update-check。gowitness 支持 Chrome 路径/代理/JSONL；尚需解决浏览器每个请求的范围控制，未调用任何原生 Web 扫描。
- 最终 CI [38018126858](https://github.com/decline-llc/asm/actions/runs/38018126858) **4/4 success**，run head 为 019f6e472faa16f5dd5ee2ca0b84f1b9d1e7fe37。四环境均 ruff 全绿、**38 passed / 9 WSL deselected**、sdist/wheel 构建成功；Ubuntu 3.11/3.12 测试分别 20.62s/21.32s，Windows 3.11/3.12 分别 24.00s/29.84s。九项原生 WSL 另在本机 47 项完整回归中通过。CI 摘要保存 data/validation/oneforall-ci.json。
- 收尾只同步三份文档，代码保持已验证版本，不触发重复 CI；再次推送后核对 main SHA 和工作区，最终文档 SHA/UTC 时间保存到被忽略的 docs/PUSH_RECEIPT.local.json。公网提供商可达性和已知子域覆盖率仍未验证；下一批优先 WSL Web 工具。

## 2026-10-10 · Session 005 · 工具/输出盘点与两端网络复核

- 用户要求说明当前 Windows/WSL 已装工具、调用、输出保存/利用、去重核对、流水线搭建、API 配置、网络、最终报告与首页截图。本批完成只读盘点和操作文档，不新增扫描功能、不修改系统网络。
- 正式提权通道使用 `pwsh.exe`（Core 7.6.5）；Windows Python 3.11.9 / WSL2 Ubuntu 24.04.4 及原生安装清单已核对。`python -m asm doctor --json-output` 重测 **18/18，exit 0**，保存 data/validation/doctor-current.json。
- 只以布尔值核对 .env 搜索引擎凭据：全部为空，WSL_DISTRO=Ubuntu、WSL_USER 为发行版默认用户。当前自动引擎只有 FOFA/Quake，其余四家只有适配器；官方 Censys Platform 使用 PAT/v3，当前旧 v2 适配器尚未迁移。
- 用 Windows httpx 和 WSL OneForAll venv requests，无凭据 HEAD 抽检 GitHub/PyPI/FOFA/Quake/crt.sh/CertSpotter 主页；两端均收到 HTTP 响应，状态依次 200/200/200/301/200/404。不跟随重定向且保留 TLS 验证，只证明当时传输可达，不证明账户或搜索查询成功。证据 network-windows.json/network-wsl.json。
- 关键实网发现：两端系统 DNS，以及显式 1.1.1.1、114.114.114.114、8.8.8.8 的 UDP/TCP 53，对 example.com A 全返回 **198.18.0.122**；先前本地多解析商夹具验收保持有效，但本机显式公网上游仍受 fake-IP 影响。Stage 4/5 拒绝假地址不等于取得真实地址，全部拒绝可能没有后续 IP 目标。
- WSL Google/Cloudflare HTTPS DNS 对照均 200，得到 104.20.23.154、172.66.147.243。Windows 初次 ConnectError/Google 握手超时，后续 Cloudflare 默认信任库及两家系统 trust store 请求均在 TLS 验证开启下成功；不把超时推断为证书问题。证据 network-doh-windows.json、network-doh-windows-detail.json、network-doh-wsl.json。当前 dns.resolvers 不支持 DoH URL，本批未修改 DNS/代理/防火墙。下一实施优先建立可信解析路径，再做实网资产核对。
- 使用 spreadsheets 技能进行只读问答核验，bundled Python/openpyxl 读取现有 test xlsx，查看实际首页 PNG 与既有总表预览；未修改/重导出工作簿。test 报告八表：总表 4、equity 1、domains 1、ips 1、urls 14、systems 1、social 0、todos 14；截图 I2 相对链接指向已存在 screenshots/1.png，1280×720 Fixture Portal。是回环夹具，不是企业公网资产；data/test 下没有自动 HTML 报告。
- 只读核对已部署 naabu/nuclei/wafw00f help，均 exit 0，保存 data/validation/tool-help/；沿用上批 Web 工具 help。工具二进制存在不等于已调度，nuclei 模板集也未作为已验收能力。
- 新增 docs/OPERATIONS.md，详细说明每个工具的版本/状态/调用/输出用途、八表字段、原始证据、真实去重键与独立来源、三种模式、API 配置、网络限制。记录 p1/p2 当前顺序执行、默认 8 在它们之前，推荐显式 `...,p1,p2,8`。
- 同步 README、HANDOFF、RUNBOOK、ACCEPTANCE、COVERAGE、SOURCES 和 docs 索引。git diff --check 通过，.env、验证数据、xlsx/PNG 和 PUSH_RECEIPT.local.json 被忽略。只改 Markdown，无需重复运行已通过的 47 项测试；最新代码仍 019f6e4，既有四环境 CI 4/4 success 有效。
- 本批按用户既有授权提交并推送文档；收尾对照本地 HEAD、远端 main 与工作区，实际 SHA/UTC 和最新 doctor/联网证据入口保存到被忽略的 docs/PUSH_RECEIPT.local.json，避免正文自引用自身 SHA。

## 2026-10-10 · Session 006 · CSV/独立 HTML 报告与工具 reference

- 用户明确要求报告同时提供 CSV 与 HTML，HTML 保底查看截图；为每个工具单独编写不同情况的命令 reference。沿用既有 main 推送与及时记录授权，Windows 命令显式使用 PowerShell Core 7.6.5。
- Stage 8 与 report 命令从同一组 SQLite 行生成 xlsx、总表 CSV、七份明细 CSV 和独立 HTML。任一 .xlsx/.csv/.html 输出后缀都指定同一报告基名；八表字段契约和已有 xlsx 样式保持。CSV 为 UTF-8 BOM，保留逗号/引号/换行，文本公式前缀（含前导空白）统一转义。
- HTML 包含八张表、计数、全表搜索和截图状态，将已采集 PNG 内嵌为 data URI；不依赖外部脚本、样式或图片。所有外部字段转义，CSP 限制网络请求和非固定脚本；缺失、无权限及非 PNG 截图分别标注。未采集的图片无法靠报告恢复。默认 Stage 8 移到 p1/p2 后，显式 stages 仍需将 8 放最后。
- 新增 13 项报告测试并扩展实际浏览器集成测试。首轮 3 个失败来自测试夹具变量遮蔽及 db.asset 返回值使用错误，修正后只剩 CSP 阻止 Playwright 字符串 eval；改用 expect 等待图片天然宽度，保持生产 CSP。完整回归 **60 passed in 69.22s**，JUnit 0 failures/errors/skipped，含 9 项真实 WSL 测试，证据 data/validation/report-formats-full.xml。ruff 与 pip check 全绿。
- 初次 build --no-isolation 因原构建 venv 缺少 wheel/setuptools 版本过低失败；改用标准隔离 python -m build 成功生成 sdist/wheel，未升级项目运行环境。asm/report_html.py 已纳入包；构建输出在 data/validation/report-formats-dist/。
- 对既有 test 数据库执行 report（未重新扫描），生成实际 xlsx/CSV/HTML：总表 4、equity 1、domains 1、ips 1、urls 14、systems 1、social 0、todos 14，1 张 1280×720 首页截图。八份 CSV 与 xlsx 逐项一致；独立 HTML 移动后离线加载，搜索通过、零外部 HTTP 请求、零页面错误；禁用 JS 验证在集成测试内通过。首页和截图区实际渲染已检查，证据 data/validation/report-formats-preview/。
- docs/reference/ 共 26 文件：18 个工具、6 个搜索引擎、索引与 API 公共调用；每页记录版本/已接入状态、场景命令、输出、利用/去重/核对及排错。原生 help 保存 data/validation/reference-help/（masscan 固定版本 help 的 rc=1 为已知特殊响应）；全部 reference 链接有效。命令示例未进行公网资产扫描，手动结果没有自动导入能力。
- 本批未调用带凭据搜索接口，未修改 WSL 工具安装、系统 DNS/代理/防火墙；公共 53 返回 fake-IP 与 Censys Legacy v2 迁移等原有缺口保持明确。报告数据、验证产物、.env 和本地 push receipt 继续不提交。后续仍先建立可信 DNS 路径，再接入 WSL Web 工具。
- 已同步 README、HANDOFF、ACCEPTANCE、RUNBOOK、OPERATIONS、COVERAGE、目录/工具/测试说明；推送与新四环境 CI 的实际结果随后追加。
- 本批代码与 reference 提交 `5e8913fd5307b63f384c96be3891d7121fd9e81b`，44 个文件，git diff --cached --check 通过。已推送 main，本地与远端 refs/heads/main SHA 一致，推送后工作区干净。新四环境 CI [38025544302](https://github.com/decline-llc/asm/actions/runs/38025544302) head 与代码提交相符；最终结论随后追加。
- 最终 CI [38025544302](https://github.com/decline-llc/asm/actions/runs/38025544302) **run success、4/4 jobs success**。Ubuntu/Windows × Python 3.11/3.12 均完成浏览器安装、ruff、非 WSL pytest 与隔离 sdist/wheel 构建，全部无失败步骤；九项真实 WSL 在本机 60 项完整回归中通过。API 状态证据保存 data/validation/report-formats-ci.json。
- 收尾仅同步 HANDOFF/ACCEPTANCE/WORKLOG，不改已验证代码、不触发重复 CI；最终推送后核对 main SHA 与工作区，最终文档 SHA/UTC、报告/CI 证据入口与 reference 数量保存 docs/PUSH_RECEIPT.local.json。

## 2026-10-10 · Session 007 · 工具 reference 完善为操作手册

- 目标：把 `docs/reference/` 从场景命令卡片完善为可直接查阅、复用、维护的操作手册；只改文档，不改代码、不安装/升级工具、不做公网扫描。
- 依据：本机已保存的工具 help（`data/validation/reference-help/`、`tool-help/`、`web-tool-help/`）、`tools/tool-lock.json` 版本锁、以及 `asm/` 调用源码（panel 各引擎、s4–s8、tools/oneforall_runner.py、tools/dns_probe.py、tools/scanners/a_scan.py、scope/precision/db）。Windows 侧版本本机复测：Python 3.11.9、Playwright 1.63.0、httpx 0.28.1、openpyxl 3.1.5、tldextract 5.4.0、dnspython 2.9.0、asm-workbench 0.1.0；`.env` 六个引擎变量均为空（仅核对键名，未输出值）。
- 执行环境说明：本会话沙箱对 `wsl.exe` 返回 E_ACCESSDENIED，无法现场重跑 WSL `--help`/版本命令；因此 WSL 工具以**已保存的本机 help 原文 + 版本锁 + 源码**为准核对，并在各页标注证据类型（本机帮助核对/回环实测/官方文档核对/待验证）。fake-IP（198.18.0.0/15）沿用既有观测记录并标注需复测，未当作永久结论。
- 每个工具页补齐九要素：用途/场景/局限/安装位置/版本/核对日期、实际接入状态（已自动调用/只有适配器/仅安装/未安装）、输入准备与场景命令（单目标/批量/端口协议/超时/限速/并发/DNS/代理/认证/重试，且每段命令带运行环境/前置/参数含义/输出位置/预期结果/失败判定表）、原生输出格式与脱敏样例+字段解析、结果衔接与是否入 ASM 库、去重/来源/时间戳/独立复核、常见失败与排错、官方来源/证据/待验证。
- 搜索引擎页另补：`.env` 变量与认证方式（并区分含 key 的 URL 需脱敏）、查询语法（域名/IP/证书/标题/正文/组织）、分页/额度/限速、HTTP 错误/业务错误/成功空结果/截断的区分、当前代码支持范围与接口迁移（Censys Legacy v2 vs Platform v3/PAT 单列对比）。明确只有 FOFA/Quake 进主流程，其余四家仅适配器。
- 新增 6 个**未安装**调研工具专页：amass、gau、waybackurls、linkfinder、arjun、x8。全部显著标注“尚未安装、调研笔记、待安装核验”，命令/参数区分“官方文档核对”与“待安装后核对”；waybackurls 与 LinkFinder 因官方 README 抓取受限，除版本/定位外全部标待核对、不预写参数。调研只采用官方文档/官方仓库/pkg.go.dev/PyPI/crates.io 等官方渠道。
- 更新 `docs/reference/README.md` 索引：新增 6 个调研工具行；统一证据标记约定与“去重与核对总则”（域名大小写/末尾点/IDNA/范围/泛解析、端口 host+port+proto 且 TCP/UDP 分开、URL 不盲目删参、多来源合并保留来源与时间、搜索/端口/指纹/模板命中分别确认）。更新 `tools/README.md` 可选扩展行指向新专页。reference 由 26 增至 32 文件。
- 核对来源汇总：本机 help（data/validation/…）、tools/tool-lock.json、asm/ 与 tools/ 源码、官方文档（FOFA/Quake/Shodan/Censys 迁移指南/Playwright/Chrome Headless/nmap、各 ProjectDiscovery 与 ffuf/gowitness/wafw00f 仓库）、官方渠道（owasp-amass.github.io、pkg.go.dev、PyPI、crates.io）。
- 待验证项：六家搜索引擎真实账户验收、Censys Platform v3/PAT 迁移、WSL Web 工具（httpx/gowitness/ffuf/katana）接入前的范围控制回环证明、可信 DNS 路径建立后的实网一致性、6 个调研工具的安装与 `--help` 核验、masscan 完整实际扫描验收、IPv6 主动端口链路原生实测。
- 本批未修改 WSL 工具安装、系统 DNS/代理/防火墙；未调用带凭据 API；`.env`/运行数据/验证产物继续不提交。

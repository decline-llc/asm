# 实施记录

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

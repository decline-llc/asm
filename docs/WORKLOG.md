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

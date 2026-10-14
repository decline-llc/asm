# 验收状态

2026-10-12，已有工具流程接入与原 WSL 核对（表格按批次保留各自证据；最新能力与缺口清单见 WORKBENCH_CAPABILITIES.md 与 TOOL_INTEGRATION.md）。完整完成定义仍为原设计第 10 章；不可把接口存在或 fixtures 回放当作实网验收通过。

| 项目 | 当前证据 | 状态 |
|---|---|---|
| Windows / WSL 架构 | PowerShell Core 7.6.5、Windows .venv Python 3.11.9、既有 Ubuntu 24.04 WSL2 | 已验证；发行版版本有差异 |
| 静态检查 | ruff 当前全绿 | 已通过 |
| 单元与集成 | Session 006 完整 `ASM_TEST_WSL=1 pytest` 60 passed in 69.22s；XML 在 data/validation/report-formats-full.xml，0 failures/errors/skipped，含 9 项真实 WSL 验证 | 已通过，无 skip |
| 模糊资产隔离 | 单元与报告测试：D 级不进入 assets/总表 | 已通过 |
| FOFA 硬限速 | 实际 MockTransport 两次请求间隔 >=15s；超配额零请求 | 已通过 |
| 本地 HTTP | 全部注入路由发现、catch-all 区分、跳转越界先阻断 | 已通过 |
| 截图及报告 | Windows Playwright PNG；xlsx 八表字段与样式保持，CSV 总表/七明细与 xlsx 逐项一致；UTF-8 BOM、公式前缀转义、空表与截图缺失/无权限/非 PNG 明确处理 | 已通过 |
| 独立 HTML | 八表、全表搜索、CSP、HTML 转义、PNG 内嵌；单文件移动后离线/禁用 JS 均显示真实截图，零外部 HTTP 请求与页面错误；真实 test 样例首页/截图版式已检查 | 逻辑、离线与视觉核验通过 |
| 报告顺序与 reference | 默认 Stage 8 在 p1/p2 后，供应链待办进入导出；26 个 reference 文件链接检查通过，原生帮助保留本地 | 已通过；仅安装工具仍未自动接入 |
| WSL 工具部署 | 八二进制 SHA-256、Chrome、wafw00f、OneForAll 导入及固定 commit SecLists 所需字典；installed.txt 已生成 | 所需工具安装通过；SecLists 为稀疏检出 |
| OneForAll 调度 | 原生固定版本七个模块、SQLite/JSON 导出，离线 HTTP transport；阻断 socket 后无网络尝试；子 root 保留、七来源合并、双端点结果、不同 root 隔离、成功复用、空响应、503、模块/任务超时及重试 | 真实工具流程已通过；公网可达性/覆盖率待验证 |
| Stage 4 范围与失败出口 | OneForAll 后台提交、现有来源合并、root/全局范围双过滤、SaaS 排除；未导入上游未验证 IP/端口；部分失败保存其它有效结果及 review；dry-run/target-local 不启动工具 | 已通过 |
| 真实 WSL/nmap | 完成/失败 marker、二进制 tar、root nmap 3 TCP + 1 UDP ；本地 CLI 4 assets / 14 URLs / 13 routes | 已通过 |
| DNS 多上游 | WSL dnsx/dig 实际查询三组回环服务，五类记录、两跳 CNAME、CDN 指纹、0.0.0.0/fake-IP 隔离、优先地址交给 Stage 6 | 本地真实工具已通过 |
| DNS 复核与异常 | Windows 指定 IP:port 上游 A/AAAA/NXDOMAIN/超时；WSL CNAME 环路、最大跳数、恰好上限终止、悬空、超时；同上游不同来源不混入扫描结果 | 已通过 |
| DNS 报告与接管 | 域名 sheet 使用 selected，失败时不回退旧地址；可选 HTTP 指纹保存匹配文本/响应摘要并进入 todos；被动模式不探测 HTTP、CNAME/NXDOMAIN 单独不生成 takeover；追加定向回归 11 passed in 2.68s | 报告逻辑及模拟 HTTP 通过；公网待实测 |
| 18/18 doctor | Session 005 重测 exit 0，18 项全部通过；data/validation/doctor-current.json；未改工具安装 | 已重新验证部署；不证明 DNS 可信 |
| 两端公网 HTTPS | GitHub/PyPI/FOFA/Quake/crt.sh/CertSpotter 主页无凭据 HEAD，Windows/WSL 都有 HTTP 响应 | 抽检传输可达；认证 API/查询覆盖率未验证 |
| 两端公网 DNS | Session 005：系统及三个显式公共上游 UDP/TCP 53 都返回 example.com=198.18.0.122。Session 008 复测修正：系统解析仍被劫持（服务器列表含 198.18.0.2，example.com→127.0.0.1/::1），显式三家未复现 fake-IP 并返回真实地址（8.8.8.8 UDP 超时） | 已按新观测修正结论；实网可信解析由 DoH 路径承担 |
| 可信解析路径（DoH） | `dns.doh_resolvers` 加密上游：IP 字面量端点校验、TLS 校验、不跟随跳转、不读环境代理；独立来源入证据；`doh_trusted` 时成为 selected 并输出 `doh_verification`；冲突→`dns_doh_mismatch`+partial；失败回退明文；Stage 4 不再继承系统解析配置；公网回环地址以 `dns_loopback_answer` 拒绝（target_local 豁免） | 代码与离线验收通过；本机实测两个端点可用（report/validation/dns-trusted-path-20261014.json）；真实目标实网核对待授权 |
| WSL Web 工具范围契约 | 新增 32 项 `tests/unit/test_broker_scope.py`：crawl-scope 精确性、GET/HEAD 转发与回执、越界 URL→403 且无观测、预算耗尽/授权撤回必须失败、其它方法协议被拒、产物名白名单防路径穿越、跨主机 CONNECT 先拒、`scope_blocks` 进入回执；并用真实 Workbench + 回环夹具证明在范围请求落账 `isolated_http_broker`、越界请求零到达、预算耗尽账本为 started+blocked | 已通过（离线/回环）；证据 report/validation/broker-scope-unit.xml；真实 WSL 工具实跑与更广 HTTPS 浏览器路径仍需外部验收 |
| 本批单元与集成 | 新增 24 项 DoH/可信路径测试全通过；完整非 WSL 回归 **344 passed / 4 environment-blocked**（受限沙箱：2 项 Playwright 截图、1 项 MSYS openssl 管道、1 项集成截图被沙箱拒绝 spawn，均与 DNS 改动无关）；ruff 全绿（`--no-cache`） | 已通过；4 项环境阻塞据实记录，未计入通过 |
| 自有域名被动链路 | 未提供书面授权的实网测试域名/API keys；只跑离线/本地 | 待真实输入 |
| 全方法覆盖 | 基础可运行；见后续 COVERAGE.md 的明确缺口 | 不能宣称 v2.0 全项完成 |
| 多工具调度接入 | 已有工具按能力/工具独立入队：dnsx/dig、naabu/a_scan、httpx/ffuf/katana/gowitness/nuclei/wafw00f、OneForAll 隔离 live job 与 SecLists 冻结输入；`tool_options` 覆盖、独立来源/原生输出/证据 hash/双版报告/恢复；本批专项 73 通过（data/validation/external-tools-20261012.xml） | 代码接入及离线/回环通过；真实提供商账户、外部白名单与更广 HTTPS 浏览器路径待验证 |
| 原 WSL 真实回环 | 原 `Ubuntu`/WSL2、用户 longchuanli、工作区 /home/longchuanli/asm-ws；dig/dnsx、naabu/a_scan/Nmap 五项与 httpx/ffuf/katana/wafw00f/nuclei 五项均 completed，gowitness（gorod）实跑生成 1280×720 PNG 并进入双报告（data/validation/native-tools-live-20261012-150726/、external-tools-live-20261012-151602/） | 回环夹具实跑通过；Masscan 网络接口、Nmap 服务/UDP/NSE 仍待外部验收 |
| WSL 运行时守卫 | 空/不可见发行版列表不得自动创建或注销 WSL、默认复用 Ubuntu、gowitness 无图退出 0 不得算截图完成；最终相关回归 90 通过（data/validation/original-wsl-final-20261012.xml） | 已通过 |
| 单元与集成（本批） | 完整单元回归 **320 passed**（原 317 + 3 项新增 WSL 运行时守卫），JUnit 0 failures/errors/skipped（data/validation/tool-integration-unit-20261012-recheck.xml）；受限沙箱内有 3 项管道用例被拒，属环境限制，宽权限下同命令全部通过。最终代码上 CI 同构选择器 `-m "not wsl"` **324 passed / 9 deselected in 257.41s**（report/validation/unit-after-fixture-fix.xml，本地文件不入库） | 已通过 |
| 静态检查（本批） | `ruff check asm tests tools` 全绿；5 个前端探针脚本原有 11 项问题本轮清零（仅删未用导入/未用局部变量、消除歧义变量名，无行为变更） | 已通过 |
| GitHub | 本批提交链 `eeddb09`（功能接入）→ `cc97a1e`（CI 失败注解）→ `7a621a9`（DNS 夹具端口）→ `d3f33ec`（DNS 超时余量）已推送 main，本地与远端 SHA 一致；最终代码提交 `d3f33ec` 的四环境 CI [38575650738](https://github.com/decline-llc/asm/actions/runs/38575650738) **4/4 jobs success**（Ubuntu/Windows × Python 3.11/3.12：ruff、非 WSL pytest、sdist/wheel 构建）。前两次复跑失败都是 Windows 运行器环境敏感性（保留端口触发 `WinError 10013`、负载下 2s DNS 超时），已修复并在 CI 复验；首次 run 38563972959 的 ubuntu 3.12 失败至今未复现，据实记录 | 已通过；收尾仅同步文档（文档提交按 paths-ignore 不触发 CI） |

`ruff` 与 `pip check` 全绿，sdist 和 wheel 构建成功。wheel 仅包含 Python 包，运行 profiles/fixtures/init-wsl 仍需仓库 editable 安装。

Session 006 原有构建 venv 缺少 wheel 且 setuptools 65.5.0 未达到 >=68，`build --no-isolation` 未通过；标准隔离 `python -m build` 成功，不修改项目运行依赖。构建输出在 data/validation/report-formats-dist/。test 报告实际导出总表 4、equity 1、domains 1、ips 1、urls 14、systems 1、social 0、todos 14，1 张首页截图；HTML 检查摘要位于 data/validation/report-formats-preview/checks.json。这些是本地回环数据，未扫描企业公网目标。

Session 006 CI run 的 head 与上述代码 SHA 相符，API 返回的各 job/step 状态保存 data/validation/report-formats-ci.json；九项真实 WSL 在本机完整 60 项回归中通过，CI 不执行 WSL。最终文档同步不改已验证代码；main 最终 SHA、工作区状态与 UTC 时间以被忽略的 docs/PUSH_RECEIPT.local.json 为准。

DNS 脱敏证据保留在 data/validation/dns/multi-resolver/ 和 negative-cases/；OneForAll 原生离线运行文件在 data/validation/oneforall/，均不提交 Git。Session 005 的 doctor 与 Windows/WSL 网络、HTTPS DNS 对照保存在 data/validation/，详见 OPERATIONS.md。Session 008 的可信路径实测（只查询公共示例域 example.com，未接触调查目标）保存在 report/validation/dns-trusted-path-20261014.json。环境通过不代表实网资产验收完成；系统解析被劫持时 Stage 5 会拒绝回环答案并可改用配置的 DoH 端点，但未配置 DoH 的真实目标仍需先建立可信解析。真实 CDN/归属、接管及带账户 API 仍待验证。OneForAll 核心测试未访问公网提供商；主页 HEAD 抽检也不证明其七来源接口完整可用。SecLists 默认只安装版本锁列出的所需文件；完整检出由用户显式选择。

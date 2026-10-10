# AI 接力入口

当前 Session 006（2026-10-10），本批实现 CSV 与独立 HTML 报告，并建立 `docs/reference/` 工具/引擎场景命令库。先读 `docs/WORKLOG.md`、`docs/ACCEPTANCE.md`、`docs/COVERAGE.md`、`docs/RUNBOOK.md`、`docs/OPERATIONS.md`、`docs/reference/README.md`，再对照原始 v2.0 设计。

环境事实已更新：正式提权通道可执行 PowerShell Core 7.6.5；WSL2 Ubuntu 24.04.4 可用；项目 `.venv` 为 Windows Python 3.11.9。原 Session 001 的拒绝访问属于历史记录。命令必须显式使用 `pwsh.exe`，不要用 Windows PowerShell 5.1。

已验证：完整测试 60 passed in 69.22s，零失败/错误/跳过；包括 9 项真实 WSL 验证。新增报告验证覆盖 CSV/XLSX 八表一致、中文 BOM 与公式前缀转义、HTML 转义与 CSP、截图缺失/无权限/非 PNG、单文件离线显示和禁用 JavaScript、搜索，以及默认报告包含 p1/p2 结果。ruff、pip check 与隔离 sdist/wheel 构建通过。此前 OneForAll 代码 019f6e4 的四环境 CI 全绿；本批新的推送与 CI 结果以 ACCEPTANCE/WORKLOG 为准。

工具在 `/home/longchuanli/asm-ws`，固定版本在 `tools/tool-lock.json`；项目只通过 stdin/tar 管道交换数据。当前 WSL 环境需为异步工具保留 Windows Popen 客户端，否则孤儿 Linux 任务可能被回收。

远端用户指定 `https://github.com/decline-llc/asm.git`，main；代码已与远端同步，实际提交与 CI 证据看 WORKLOG，本地最终回执为 docs/PUSH_RECEIPT.local.json。不要覆盖远端已有提交，不提交 .env、运行数据、真实 targets 或未经脱敏的 fixtures。

环境 Session 005 重测 18/18，未改工具安装。SecLists 为固定 commit 的所需字典稀疏检出；OneForAll 使用独立 venv 的兼容依赖。优先接续：先建立可信 DNS 路径，再按 COVERAGE 补齐 WSL Web 工具（httpx/gowitness/ffuf/katana）、真实 API/第三方浏览、共享配额和并行调度。Windows/WSL 的系统及显式 1.1.1.1/114.114.114.114/8.8.8.8 UDP/TCP 53 都把 example.com 返回为 198.18.0.122；仅指定上游仍未避开 fake-IP。HTTPS DNS 对照取得公网地址，Windows 曾连接超时后成功；现有 dns.resolvers 不支持 DoH URL。Stage 4/5 过滤假地址不会找回真实地址。本批未修改系统 DNS/代理/防火墙。自有域名/API keys 未提供，不能把回环或主页 HEAD 当成真实资产/认证 API 验收。

OPERATIONS.md 已逐项说明安装与调度差别：主流程自动引擎目前仅 FOFA/Quake，另外四家只有适配器；Censys 仍为 Legacy v2，Platform PAT 迁移待做。报告命令和 Stage 8 默认同时生成 xlsx、总表 CSV、七份明细 CSV 与独立 HTML；HTML 内嵌已采集 PNG，无外部脚本/样式/图片，缺失截图明确标注。三种输出后缀都可指定报告基名。p1/p2 当前顺序执行，默认 Stage 8 已放在它们之后；自定义 stages 仍需将 8 放最后。所有凭据为空，现有 test 报告为本地 fixture（4 资产、14 URLs、14 todos、1 首页截图）。

docs/reference/ 共 26 页：18 个工具、6 个搜索引擎及索引/API 公共调用页，记录固定版本、已接入状态、场景命令、原生输出、利用/去重/核对与排错。命令示例不等于新增调度能力，也没有自动导入手动运行结果。帮助文本在 data/validation/reference-help/；真实样例和离线页面检查在 data/validation/report-formats-preview/。本批未执行公网目标扫描或带凭据 API 查询，未修复既有 DNS fake-IP 问题。

DNS 原始解析观测位于阶段目录 dns-observations.json；按来源、上游、差异及 CNAME 状态组织的证据在 dns-evidence.json；可用记录在 dns.json/SQLite。Stage 6 和报告优先读取 facts 中 selected；解析失败时不会从旧记录恢复扫描地址。CNAME 外部终点只是证据，不扩大目标白名单。takeover_probe 默认关闭，开启后只在主动授权模式请求原始域名，指纹命中也只标 review。

OneForAll 调度现已接入 Stage 4。固定 v0.4.5 主流程即使关闭 brute/dns/req 仍触发 wildcard/SRV，且会转成注册域；只能使用本项目 `tools/oneforall_runner.py` 的 Collect + 原生 SQLite/JSON 导出路径。默认五模块，支持七个公开来源；HTTP 主机白名单、关闭重定向、TLS 验证、8 MiB 上限；目标/付费模块不允许。日志、数据库与临时文件每任务独立，第三方源码不改。先导出去重前观测保留所有来源；AlienVault 两接口在进程中取并集。只入库范围内域名，工具 IP/端口不作为资产证据。成功任务可复用，模块/HTTP 失败 rc=2、整任务超时 rc=124，结果部分保留并进入 review；原生离线流程已验证，公网可达性/覆盖率待真实输入。

WSL Web 工具帮助已只读核对，保存在 data/validation/web-tool-help/。httpx 使用 -j/-r/-allow/-duc，保持默认不跟随跳转；ffuf 默认不跳转，需设置 -rate 并解析原生 JSON；katana 默认 -fs rdn 且跟随跳转，接入必须指定精确 crawl-scope、-dr/-duc，回环验证越界请求零到达。gowitness scan file 支持 --chrome-path/--chrome-proxy/--write-jsonl，但浏览器子资源/导航的范围约束尚待实现，不可仅依赖输入 URL 过滤便启用。

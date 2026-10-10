# AI 接力入口

当前 Session 004（2026-10-10），已在 DNS/CDN 基础上完成 OneForAll 被动调度批次。先读 `docs/WORKLOG.md`、`docs/ACCEPTANCE.md`、`docs/COVERAGE.md`、`docs/RUNBOOK.md`，再对照原始 v2.0 设计。

环境事实已更新：正式提权通道可执行 PowerShell Core 7.6.5；WSL2 Ubuntu 24.04.4 可用；项目 `.venv` 为 Windows Python 3.11.9。原 Session 001 的拒绝访问属于历史记录。命令必须显式使用 `pwsh.exe`，不要用 Windows PowerShell 5.1。

已验证：完整测试 47 passed in 64.58s，无 skip；包括离线核心、本地 HTTP/截图/八表报告/15s 配额、真实 WSL 后台回收与 root nmap、原生 dnsx/dig 三上游与 CNAME 异常，以及真实 OneForAll 核心离线 HTTP 流程。接管候选已进入报告 todos。WSL 上游按 dig → Windows → dnsx 选择可用观测，各来源保留；默认优先 114.114.114.114。推送及最新四环境 CI 以 ACCEPTANCE/WORKLOG 的实际结果为准。

工具在 `/home/longchuanli/asm-ws`，固定版本在 `tools/tool-lock.json`；项目只通过 stdin/tar 管道交换数据。当前 WSL 环境需为异步工具保留 Windows Popen 客户端，否则孤儿 Linux 任务可能被回收。

远端用户指定 `https://github.com/decline-llc/asm.git`，main；代码已与远端同步，实际提交与 CI 证据看 WORKLOG，本地最终回执为 docs/PUSH_RECEIPT.local.json。不要覆盖远端已有提交，不提交 .env、运行数据、真实 targets 或未经脱敏的 fixtures。

环境在 Session 002 已验收 18/18，本批未改工具安装。SecLists 为固定 commit 的所需字典稀疏检出；OneForAll 使用独立 venv 的兼容依赖。优先接续：按 COVERAGE 补齐 WSL Web 工具（httpx/gowitness/ffuf/katana），再补真实 API/第三方浏览、共享配额和并行调度。先核对固定版本 help，并确保原生工具的跳转/爬取仍遵守现有每跳范围规则，用 WSL 回环夹具验收。系统 DNS 仍有代理 fake-IP；Stage 4 字典与 Stage 5 使用配置上游并默认拒绝 198.18.0.0/15，未修改系统 DNS。其它工具和 HTTP 仍需各自的可信解析；自有域名实网验收缺少用户指定目标与 keys，默认/演示不能当作真实授权。

DNS 原始解析观测位于阶段目录 dns-observations.json；按来源、上游、差异及 CNAME 状态组织的证据在 dns-evidence.json；可用记录在 dns.json/SQLite。Stage 6 和报告优先读取 facts 中 selected；解析失败时不会从旧记录恢复扫描地址。CNAME 外部终点只是证据，不扩大目标白名单。takeover_probe 默认关闭，开启后只在主动授权模式请求原始域名，指纹命中也只标 review。

OneForAll 调度现已接入 Stage 4。固定 v0.4.5 主流程即使关闭 brute/dns/req 仍触发 wildcard/SRV，且会转成注册域；只能使用本项目 `tools/oneforall_runner.py` 的 Collect + 原生 SQLite/JSON 导出路径。默认五模块，支持七个公开来源；HTTP 主机白名单、关闭重定向、TLS 验证、8 MiB 上限；目标/付费模块不允许。日志、数据库与临时文件每任务独立，第三方源码不改。先导出去重前观测保留所有来源；AlienVault 两接口在进程中取并集。只入库范围内域名，工具 IP/端口不作为资产证据。成功任务可复用，模块/HTTP 失败 rc=2、整任务超时 rc=124，结果部分保留并进入 review；原生离线流程已验证，公网可达性/覆盖率待真实输入。

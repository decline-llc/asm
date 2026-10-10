# AI 接力入口

当前 Session 003（2026-10-10），已在基础版本上完成 DNS/CDN 批次。先读 `docs/WORKLOG.md`、`docs/ACCEPTANCE.md`、`docs/COVERAGE.md`、`docs/RUNBOOK.md`，再对照原始 v2.0 设计。

环境事实已更新：正式提权通道可执行 PowerShell Core 7.6.5；WSL2 Ubuntu 24.04.4 可用；项目 `.venv` 为 Windows Python 3.11.9。原 Session 001 的拒绝访问属于历史记录。命令必须显式使用 `pwsh.exe`，不要用 Windows PowerShell 5.1。

已验证：完整测试 35 passed，无 skip；包括离线核心、本地 HTTP/截图/八表报告/15s 配额、真实 WSL 后台回收与 root nmap，以及原生 dnsx/dig 三上游、两跳 CNAME、环路/上限/悬空/超时。接管候选已进入报告 todos，追加定向回归 11 passed。WSL 上游按 dig → Windows → dnsx 选择可用观测，各来源保留；默认优先 114.114.114.114。最新代码 385c02d 已推送 main，四环境 CI 全部通过；链接及证据以 ACCEPTANCE 为准。

工具在 `/home/longchuanli/asm-ws`，固定版本在 `tools/tool-lock.json`；项目只通过 stdin/tar 管道交换数据。当前 WSL 环境需为异步工具保留 Windows Popen 客户端，否则孤儿 Linux 任务可能被回收。

远端用户指定 `https://github.com/decline-llc/asm.git`，main；代码已与远端同步，实际提交与 CI 证据看 WORKLOG，本地最终回执为 docs/PUSH_RECEIPT.local.json。不要覆盖远端已有提交，不提交 .env、运行数据、真实 targets 或未经脱敏的 fixtures。

环境在 Session 002 已验收 18/18，本批未改工具安装。SecLists 为固定 commit 的所需字典稀疏检出；OneForAll 使用独立 venv 的兼容依赖。优先接续：按 COVERAGE 接入 OneForAll 调度，然后补齐 WSL Web 工具、真实 API/第三方浏览、共享配额和并行调度。系统 DNS 仍有代理 fake-IP；Stage 4 字典与 Stage 5 使用配置上游并默认拒绝 198.18.0.0/15，未修改系统 DNS。其它工具和 HTTP 仍需各自的可信解析；自有域名实网验收缺少用户指定目标与 keys，默认/演示不能当作真实授权。

DNS 原始解析观测位于阶段目录 dns-observations.json；按来源、上游、差异及 CNAME 状态组织的证据在 dns-evidence.json；可用记录在 dns.json/SQLite。Stage 6 和报告优先读取 facts 中 selected；解析失败时不会从旧记录恢复扫描地址。CNAME 外部终点只是证据，不扩大目标白名单。takeover_probe 默认关闭，开启后只在主动授权模式请求原始域名，指纹命中也只标 review。

下一批 OneForAll 接入前，已在本机原生 WSL v0.4.5 执行 `oneforall.py --help`，exit 0。其 brute/dns/req 默认均开启，不能直接调用默认 run 作为被动枚举；应显式关闭这些开关及 takeover，并设置 alive=False 保留未验证子域，后续交给 Stage 5。先核对 --fmt=json/--path 的实际文件格式，再增加来源与 scope 过滤、超时/失败/幂等证据；不得把安装/导入或 help 通过当成调度已实现。

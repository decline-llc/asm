# AI 接力入口

当前 Session 002，已恢复执行并构建可运行基础版本。先读 `docs/WORKLOG.md`、`docs/ACCEPTANCE.md`、`docs/COVERAGE.md`、`docs/RUNBOOK.md`，再对照原始 v2.0 设计。

环境事实已更新：正式提权通道可执行 PowerShell Core 7.6.5；WSL2 Ubuntu 24.04.4 可用；项目 `.venv` 为 Windows Python 3.11.9。原 Session 001 的拒绝访问属于历史记录。命令必须显式使用 `pwsh.exe`，不要用 Windows PowerShell 5.1。

已验证：完整测试 22 passed，无 skip；包括离线核心、本地 HTTP/截图/八表报告/15s 配额、真实 WSL 后台回收与 root nmap。最新工具部署与远端状态以 ACCEPTANCE 为准。

工具在 `/home/longchuanli/asm-ws`，固定版本在 `tools/tool-lock.json`；项目只通过 stdin/tar 管道交换数据。当前 WSL 环境需为异步工具保留 Windows Popen 客户端，否则孤儿 Linux 任务可能被回收。

远端用户指定 `https://github.com/decline-llc/asm.git`，main；本地已初始化，推送进展看 WORKLOG。不要覆盖远端已有提交，不提交 .env、运行数据、真实 targets 或未经脱敏的 fixtures。

优先接续：完成工具安装/doctor；按 COVERAGE 补齐 OneForAll、dnsx/dig、WSL Web 工具、真实 API/第三方浏览、共享配额和并行调度。自有域名实网验收缺少用户指定目标与 keys；默认/演示不能当作真实授权。

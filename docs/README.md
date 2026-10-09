# 工程文档

接力顺序：根目录 `HANDOFF.md` → `WORKLOG.md` → `ACCEPTANCE.md` → `COVERAGE.md` → `RUNBOOK.md`。

- WORKLOG：每批次实际改动、命令、结果、失败与恢复，持续追加。
- ACCEPTANCE：以原设计 DoD 对照可重跑证据，不把模拟测试当成实网测试。
- COVERAGE：已实现能力与明确缺口，下一位 AI 据此补齐。
- RUNBOOK：本机环境、安装、离线演示、本地验证及推送流程。
- SOURCES：固定版本与 API 的官方出处。

推送记录在 WORKLOG 中保留实际命令、分支、提交和远端核验。运行日志/密钥保留在被忽略的 data/.env 中，不提交 Git。

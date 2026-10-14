# 工程文档

ASM Workbench当前需求与接力入口：本地`audits/CHATGPT_NEXT_ROUND_PROMPT.md`（完整阅读，尤其§10），再核对实际代码、配置与留档证据。[WORKBENCH_CAPABILITIES.md](WORKBENCH_CAPABILITIES.md)记录通用能力接入与验收缺口。根目录HANDOFF/WORKLOG/ACCEPTANCE/COVERAGE/RUNBOOK作为历史背景，不覆盖最新确认需求。

- WORKLOG：每批次实际改动、命令、结果、失败与恢复，持续追加。
- ACCEPTANCE：以原设计 DoD 对照可重跑证据，不把模拟测试当成实网测试。
- COVERAGE：已实现能力与明确缺口，下一位 AI 据此补齐。
- RUNBOOK：本机环境、安装、离线演示、本地验证及推送流程。
- [tools/README.md](../tools/README.md)：当前暴露面扫描工具清单，分类记录用途、工作台/兼容阶段接入状态、版本及运行依赖。
- [TOOL_INTEGRATION.md](TOOL_INTEGRATION.md)：已有工具的完整流程接入、独立多工具步骤、外部HTTP隔离代理、配置与验收状态。
- OPERATIONS：历史部署的调用与输出、API 配置、去重核对、流水线顺序、网络实测及最终报告；当前工具接入以工具清单为准。
- [reference/README.md](reference/README.md)：每工具/引擎一个文件，按场景记录命令、输出、版本与故障处理。
- SOURCES：固定版本与 API 的官方出处。
- [audits/](audits/)：AI 执行/审查轮次文档集中地——审阅提示词与报告（GLM、第二轮复核）、
  修复交接（Kimi）、预览说明、跨模型交接（ChatGPT）及 `review-artifacts/` 过程证据。
  其中 `audits/CHATGPT_NEXT_ROUND_PROMPT.md` 含真实目标数据，被 .gitignore 排除（本地专用）。

推送记录在 WORKLOG 中保留实际命令、分支、提交和远端核验。运行日志/密钥保留在被忽略的 data/.env 中，不提交 Git。
真实目标的交付（证据/工具/报告/账本）只存在于本地被忽略的 `report/<target>_delivery/`，不提交 Git。

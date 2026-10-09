# 验收状态

2026-10-09，Session 002。完整完成定义仍为原设计第 10 章；不可把接口存在或 fixtures 回放当作实网验收通过。

| 项目 | 当前证据 | 状态 |
|---|---|---|
| Windows / WSL 架构 | PowerShell Core 7.6.5、Windows .venv Python 3.11.9、既有 Ubuntu 24.04 WSL2 | 已验证；发行版版本有差异 |
| 静态检查 | ruff 当前全绿 | 已通过 |
| 单元与集成 | 修复后完整 `pytest` 22 passed in 24.66s；XML 在 data/validation/pytest.xml | 已通过，无 skip |
| 模糊资产隔离 | 单元与报告测试：D 级不进入 assets/总表 | 已通过 |
| FOFA 硬限速 | 实际 MockTransport 两次请求间隔 >=15s；超配额零请求 | 已通过 |
| 本地 HTTP | 全部注入路由发现、catch-all 区分、跳转越界先阻断 | 已通过 |
| 截图及报告 | Windows Playwright PNG、相对行号链接、8 sheet 字段契约；Artifact Tool 只读渲染并逐页检查八张表 | 逻辑与视觉核验通过 |
| WSL 工具部署 | 八二进制 SHA-256 完成；其余工具部署继续中 | 部分通过 |
| 真实 WSL/nmap | 完成/失败 marker、二进制 tar、root nmap 3 TCP + 1 UDP ；本地 CLI 4 assets / 14 URLs / 13 routes | 已通过 |
| 18/18 doctor | 尚未完成执行 | 待验证 |
| 自有域名被动链路 | 未提供书面授权的实网测试域名/API keys；只跑离线/本地 | 待真实输入 |
| 全方法覆盖 | 基础可运行；见后续 COVERAGE.md 的明确缺口 | 不能宣称 v2.0 全项完成 |
| GitHub | 本地仓库与 origin 已建立；尚未推送 | 待推送 |

`ruff` 与 `pip check` 全绿，sdist 和 wheel 构建成功。wheel 仅包含 Python 包，运行 profiles/fixtures/init-wsl 仍需仓库 editable 安装。

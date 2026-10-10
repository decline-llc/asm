# ASM Workbench

根据《暴露面收集框架 — 工程实施设计 v2.0》构建的授权暴露面收集与资产治理框架。Windows Python 负责编排、SQLite 和报告；外部扫描工具全部在 WSL 原生文件系统内运行，通过管道交换结果。

当前为可运行基础版本：47 项离线/本地/真实 WSL 测试通过；本地 CLI 已完成 TCP/UDP → Web → 截图 → 报告链路。Stage 4 已接入 OneForAll 七来源白名单被动采集（默认五个）、来源合并和失败/超时证据。DNS 阶段使用 dnsx/dig 多上游、Windows 显式复核、CNAME 链和地址修正；端口与域名报告使用选择后的地址。完整设计仍有缺口，见 `docs/COVERAGE.md`；验收证据见 `docs/ACCEPTANCE.md`。AI 接力入口为 `HANDOFF.md`，过程记录为 `docs/WORKLOG.md`。

原始设计和两份 HTML 保留在仓库根目录。运行数据库、API 密钥、真实目标结果不提交 Git。

## 开始使用

在 PowerShell 7 中，用 Windows Python 3.11+ 创建 `.venv`，运行 `pip install -e .[dev,browser]`、`python -m playwright install chromium`。复制 `.env.example` 为 `.env`，指定已有 WSL distro 名称，再运行：

```powershell
.\.venv\Scripts\python.exe -m asm init-wsl --distro Ubuntu
.\.venv\Scripts\python.exe -m asm doctor
.\.venv\Scripts\python.exe -m asm run --profile demo --stages 1,2a,2b,3,4,5,p1,p2,8 --dry-run --passive-only
$env:ASM_TEST_WSL='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/local-demo.py
```

项目当前采用仓库内 editable 安装；profiles、部署脚本与 fixtures 依赖仓库目录，单独 wheel 只包含编排包。安装详见 `docs/RUNBOOK.md`；工具/API/输出/去重/报告说明见 [docs/OPERATIONS.md](docs/OPERATIONS.md)。2026-10-10 两端实测发现显式公共 DNS 的 UDP/TCP 53 仍返回 fake-IP，实网资产核对前需建立可信解析路径。

`default` 无主动授权；`demo` 只回放脱敏输入；`test` 只允许回环 fixture。配置 `authorization: true` 和白名单才可运行主动模块。外部二进制、字典与工具结果全部放在 WSL 原生文件系统。

## 目录

`asm/` 编排包，`profiles/` 项目配置，`scripts/` 部署与演示，`tools/` 版本锁与分类，`tests/` 离线/本地验证，`docs/` 工程记录，`data/` 被忽略的运行结果。各目录均有 README。

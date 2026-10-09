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

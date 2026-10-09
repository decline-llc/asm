# 运行手册

本机仓库 `D:\Desktop\asm`，PowerShell 7 Core；项目 `.venv` 使用 Windows Python 3.11.9。已有 WSL2 distro 名为 `Ubuntu`，Ubuntu 24.04.4 LTS，默认用户 longchuanli，原生工作区 `/home/longchuanli/asm-ws`。

```powershell
# PowerShell 7 Core 中运行
.\.venv\Scripts\python.exe -m asm --help
.\.venv\Scripts\python.exe -m asm doctor
.\.venv\Scripts\python.exe -m asm init-wsl --distro Ubuntu
.\.venv\Scripts\python.exe -m asm run --profile demo --stages 1,2a,2b,3,4,5,p1,p2,8 --dry-run --passive-only
.\.venv\Scripts\python.exe -m asm run --profile demo --stages 1,2a,2b,3,4,5,p1,p2,8 --dry-run --passive-only --resume
$env:ASM_TEST_WSL='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/local-demo.py
.\.venv\Scripts\python.exe -m asm report --profile test
```

初次创建 venv 用本机已有 `D:\.pyenv\pyenv-win\versions\3.11.9\python.exe -m venv .venv`，然后 `pip install -e .[dev,browser]` 和 `python -m playwright install chromium`。不要改 pyenv 全局默认版本。

WSL apt 如被系统自动更新占锁，等待释放。若提示 dpkg interrupted，先按实际 audit 修复；不要删除锁或杀自动更新进程。网络若受 Windows loopback 代理影响，使用可达的宿主网关代理做本次命令配置，不改系统默认 DNS/防火墙。

首次远端交付使用 main，`origin=https://github.com/decline-llc/asm.git`；按用户明确要求完成推送，不覆盖远端其它人的提交。推送前 `git status`、`git diff --check`、检查 .env/data 被忽略，推送后对照 `git rev-parse HEAD` 和 `git ls-remote origin refs/heads/main`。

本机 GCM 有多个账号；仓库级 `credential.https://github.com.username=decline-llc` 已指定推送身份，凭据仍由 GCM 管理。不要把令牌写进 remote URL、配置模板或日志。

SecLists 默认按 `tools/tool-lock.json` 固定版本稀疏检出所需字典。完整安装可在 WSL 中执行 `ASM_SECLISTS_FULL=1 ASM_WS=/home/longchuanli/asm-ws bash /home/longchuanli/asm-ws/wsl-setup.sh`；其它外部工具已安装时可加 `ASM_SKIP_APT=1`。不要在未完成 clone 的目录上执行版本检查或覆盖用户改动。

Windows CLI 也可在本次调用前设置 `$env:ASM_SKIP_APT='1'` 或 `$env:ASM_SECLISTS_FULL='1'`，bootstrap 只接收 0/1 并显式传入 WSL。APT 阶段须 root；新机器执行完整安装，不跳过 APT。

当前系统 DNS 受本机代理 fake-IP 影响，`example.com` 返回 198.18.0.0/15 地址。doctor 的网络检查仅证明 DNS 可响应；真实 DNS/CDN/归属验收需要在配置中指定可信上游或由用户调整代理模式。

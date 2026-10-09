# 脚本

- `deploy-wsl.py`：Windows Python stdlib bootstrap，stdin 管道传输安装脚本、锁和备用扫描器，然后在 WSL root 安装。
- `wsl-setup.sh`：固定版本和校验摘要的 WSL 安装脚本，重复执行复用已下载工具；root 安装完后 bootstrap 把工作区归还发行版默认用户。
- `local-demo.py`：Windows 与 WSL 各自启动仅回环监听的脱敏 fixture，运行 CLI 流水线并导出截图/报表；最后停止它自己创建的进程。

Windows 命令必须从 PowerShell 7 Core 执行。项目 Python 用 `.venv/Scripts/python.exe`。不要更改系统默认 pyenv 版本或在 Windows 安装外部扫描器。

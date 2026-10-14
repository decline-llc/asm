# 脚本

- `deploy-wsl.py`：Windows Python stdlib bootstrap，stdin 管道传输安装脚本、锁和备用扫描器，然后在 WSL root 安装。
- `wsl-setup.sh`：固定版本和校验摘要的 WSL 安装脚本，重复执行复用已下载工具；root 安装完后 bootstrap 把工作区归还发行版默认用户。
- `inspect_tool_runtime.py`：只读核对选定的原有WSL用户、工具工作区、版本和资源commit；默认Ubuntu，不读取密钥、不扫描目标。
- `prepare_tool_runtime.py`：在批准系统/网络安装后，对选定的已存在WSL调用固定版本部署；默认复用Ubuntu，不创建或注销发行版；不读取.env、不扫描目标。
- `external_tool_acceptance.py`：六个外部HTTP工具针对自有loopback fixture真实运行，记录独立验证工作区与双版报告；需要已部署WSL及namespace代理依赖。
- `native_tool_acceptance.py`：原WSL内自建回环DNS/HTTP夹具，验证dig/dnsx、naabu/a_scan/Nmap及双版报告；保留原工具安装，结束后关闭自有夹具。
- `local-demo.py`：Windows 与 WSL 各自启动仅回环监听的脱敏 fixture，运行 CLI 流水线并导出截图/报表；最后停止它自己创建的进程。

Windows 命令必须从 PowerShell 7 Core 执行。项目 Python 用 `.venv/Scripts/python.exe`。不要更改系统默认 pyenv 版本或在 Windows 安装外部扫描器。

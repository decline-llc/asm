# 工具分类与部署

仓库只保存安装锁、包装器与说明，不保存下载二进制和第三方源码。实际运行目录为 WSL 原生 `~/asm-ws/`。

| 类别 | 工具 | WSL 位置 |
|---|---|---|
| 被动收集 | subfinder、OneForAll | bin/、tools/OneForAll/.venv/ |
| DNS | dnsx、dig | bin/、/usr/bin/ |
| 端口/服务 | nmap、masscan、naabu、a_scan.py | /usr/bin/、bin/、tools/ |
| Web | httpx、katana、ffuf、gowitness、wafw00f、Chrome | bin/、tools/wafw00f/.venv/、/usr/bin/ |
| 模板工具 | nuclei | bin/；当前流水线不自动执行漏洞模板 |
| 字典 | SecLists | wordlists/SecLists/ |
| 可选扩展 | Amass、gau、waybackurls、LinkFinder、arjun、x8 | 后续单独选择安装；当前未安装 |

八个二进制的版本、官方 URL 与 SHA-256 见 `tool-lock.json`。安装前校验下载摘要，重复安装复用已经校验的缓存。APT 包与 Chrome 版本在 WSL `manifests/installed.txt` 中记录；Python 工具各有独立 venv，兼容 Ubuntu 的 externally-managed Python。

当前会话使用已有 `Ubuntu` 24.04 发行版。本机 `.env` 指定 `WSL_DISTRO=Ubuntu`；模板仍为设计的 `Ubuntu-22.04`。安装入口：`python -m asm init-wsl --distro Ubuntu`。

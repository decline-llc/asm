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

SecLists 2026.1 文件总量约 1.96GB。默认使用固定 commit 的 partial clone 与 sparse checkout，安装版本锁指定的 raft-medium 四份 Web 字典、top-5000 DNS 字典、README 和许可证。需要其它字典时，在 WSL 原生目录扩展 sparse-checkout；安装时设置 `ASM_SECLISTS_FULL=1` 可取回完整版本。已完整检出的仓库会保留现有文件。

OneForAll 上游 requirements 的 exrex 0.10.5 与 Python 3.11+ 不兼容；bootstrap 生成有效 requirements，只将该版本替换为 0.12.0，并安装 setuptools 75.8.0 的 distutils shim。这些兼容依赖都位于 OneForAll 独立 venv，原源码及 requirements 保留。

所需字典通过官方 raw 固定 commit 地址下载，并按该 Git tree 的 blob SHA 逐一校验后写入本地 Git object store，再完成 sparse checkout。这样可复用元数据并处理 WSL 下 Git lazy-fetch 第二连接超时，不跳过哈希校验。最终环境自检 18/18 已通过。

`dns_probe.py` 是 stdlib 原生 WSL dig 包装器。编排将它与 `asm/utils/dns.py`（任务内命名 dns_support.py）、targets.json 通过 stdin 写入任务目录，按指定上游查询五类记录并有界追踪 CNAME。它不从 /mnt 导入 Windows 包，不依赖 WSL dnspython，也不更改系统 resolver。dnsx 独立按每个上游执行，其观测与 dig 结果分别保留。

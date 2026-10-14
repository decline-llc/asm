# 当前暴露面扫描工具清单与部署

核对日期：2026-10-12，Asia/Shanghai。按当前代码、[模式配置](../profiles/modes.yaml)及[版本锁](tool-lock.json)整理；工作台使用 schema2，旧 Stage 流水线作为兼容入口保留。下表的“已接入”表示已有执行适配器，实际执行还取决于项目选择、权限、输入、凭据及运行依赖；本地/离线验收覆盖见 [WORKBENCH_CAPABILITIES](../docs/WORKBENCH_CAPABILITIES.md)。

本批接入实现、完整流程分工、配置及验收说明见 [TOOL_INTEGRATION](../docs/TOOL_INTEGRATION.md)。工作台现在支持同能力多个工具的独立步骤及 `tool_options` 参数覆盖；dig/dnsx、naabu/a_scan/Nmap及六个HTTP工具已在原Ubuntu完成回环验收，gowitness以gorod实际PNG为准。公开来源、账户及非回环验收独立记录。

2026-10-12正式主机权限下核对：原默认发行版为 `Ubuntu`、WSL2，用户 `longchuanli`，原生工作区 `/home/longchuanli/asm-ws` 完整存在；主要二进制版本、OneForAll和SecLists commit与版本锁一致，Chrome及namespace依赖已安装。此前受限进程返回空列表，不能据此认定用户没有WSL。误新增的独立 `Ubuntu-24.04` 已停止部署并终止，未删除或迁移原环境，后续复用原 `Ubuntu`。Windows `.venv` 实测版本：Python httpx 0.28.1、dnspython 2.9.0、Playwright 1.63.0。

## 1. 搜索引擎与被动收集

| 工具 / 来源 | 用途 | 工作台接入状态 / 入口 |
|---|---|---|
| [FOFA](../docs/reference/fofa.md) | 域名/IP资产索引、证书等关联线索 | 已接入独立 `search` 步骤；需 `FOFA_EMAIL`、`FOFA_KEY` |
| [Quake](../docs/reference/quake.md) | 域名/IP及服务资产索引 | 已接入独立 `search` 步骤；需 `QUAKE_TOKEN` |
| [Hunter](../docs/reference/hunter.md) | 域名/IP及Web资产索引 | 已接入独立 `search` 步骤；需 `HUNTER_KEY` |
| [ZoomEye](../docs/reference/zoomeye.md) | 域名/IP及服务资产索引 | 已接入独立 `search` 步骤；需 `ZOOEYE_KEY` |
| [Shodan](../docs/reference/shodan.md) | IP、端口与服务资产索引 | 已接入独立 `search` 步骤；需 `SHODAN_KEY` |
| [Censys](../docs/reference/censys.md) | 主机与服务资产索引 | 已接入独立 `search` 步骤；适配器仍调用 Search v2，需 `CENSYS_ID`、`CENSYS_SECRET` |
| [subfinder](../docs/reference/subfinder.md) 2.17.0 | 被动子域收集 | `passive_subdomains: subfinder` 已接入，依赖 WSL；旧 Stage 4 也调用 |
| [OneForAll](../docs/reference/oneforall.md) v0.4.5 | 多来源被动子域收集 | 工作台 `oneforall_passive` 已接隔离live job及留档导入，均校验被动flags；依赖WSL，新增live job实跑待验收 |
| crt.sh / `certificate_indexes` | 从证书透明度索引提取子域候选 | 已接入 `passive_subdomains`，查询第三方索引 |
| Wayback CDX / `archive_indexes` | 从历史URL索引提取子域候选 | 已接入 `passive_subdomains`，查询第三方索引 |
| HackerTarget / `hostsearch` | 公开主机与子域线索 | 仅旧 Stage 4 已接入；工作台尚未接入该来源 |
| Sourcegraph / `sourcegraph_stream` | 公开代码索引中的系统、人员及关联线索 | 已接入 `osint`；支持流式查询与已保存 SSE，外网验收待补 |
| `company_evidence_import`、`tender_import`、`osint_evidence_import`、`saved_supply_analysis` | 工商/股权/备案、招投标与供应链证据导入和分析 | 已接入内部适配器；工商备案 live provider 尚未接入，供应链分析使用已有证据 |

六家搜索引擎均有代码适配器；本清单不读取账户密钥、不发起API查询，账户及外部响应验收以实际运行证据为准。

## 2. 工作台主动扫描与核查

| 工具 / 内置模块 | 用途 | 接入状态 / 范围 |
|---|---|---|
| [Nmap](../docs/reference/nmap.md) | TCP/UDP端口、服务版本及批准的NSE脚本 | 已接入 `tcp_scan`、`udp_scan`、`service_probe`、`deep_service_probe`；新版TCP在原WSL回环实跑通过，服务/UDP/NSE以专项/历史证据为准 |
| [Masscan](../docs/reference/masscan.md) | IPv4 TCP端口快速发现 | 已接入 `tcp_scan`；依赖 WSL，新版分批/恢复为Mock验证。旧 Stage 6 可选并衔接 Nmap 服务确认 |
| `python_socket` | TCP connect / UDP响应观测 | 已接入 `tcp_scan`、`udp_scan`，须显式选择；无服务版本识别，UDP无响应保持未知/过滤候选 |
| [dnspython 2.9.0](../asm/active_tools.py) / `dnspython_dictionary` | A/AAAA/MX/NS/CNAME解析、CNAME链与DNS字典枚举 | 已接入 `dns_recursive`、`dns_enum`；Windows原生，多上游/并发/检查点 |
| Python httpx / `target_http` | Web访问、响应状态/标题/内容线索 | 已接入 `web_visit` 及内部HTTP请求；与 ProjectDiscovery httpx 二进制分别管理 |
| [Playwright + Chromium](../docs/reference/playwright.md) | 页面及登录页截图 | 已接入 `screenshot`；Windows浏览器运行时，逐请求范围和预算控制 |
| `native_tls` | TLS证书、握手与协议观测 | 已接入 `tls_inspect`；连接显式IP或localhost，不等同完整密码套件枚举 |
| `native_crawler` | Web链接与页面爬取 | 已接入 `web_crawl`；深度、URL数和请求预算控制 |
| `native_js_analyzer` | JS文件中的候选端点提取 | 已接入 `js_analysis`；发现端点不自动核实 |
| `stage_7_paths` | 内置/配置字典路径枚举、随机基线对照 | 已接入 `web_path_enum`；实际请求由 `target_http` 执行 |
| `stage_7_exposure` | 配置、备份、源码元数据、管理页面、API schema暴露候选 | 已接入 `exposure_check`；按批准类别检查，结果待复核 |
| `native_risk_checks` | 安全响应头、CORS策略核查 | 已接入 `vulnerability_check`；目前仅 `security_headers`、`cors_policy` |
| `stage_5_takeover_fingerprint` | 已有CNAME证据结合提供商HTTP特征 | 已接入 `takeover_probe`；输出接管候选，不申领资源 |
| `native_auth_audit` | 明确受保护路径的匿名访问观察 | 已接入 `auth_audit`；凭据认证及弱口令扩展尚未接入 |

执行注册与实现依据：[workbench_tools.py](../asm/workbench_tools.py)、[active_tools.py](../asm/active_tools.py)、[passive_indexes.py](../asm/passive_indexes.py)、[passive_tools.py](../asm/passive_tools.py)。

## 3. 兼容阶段工具、手动工具与运行资源

下列固定版本于2026-10-12在原 `Ubuntu` 中重新查询；OneForAll、SecLists commit与锁一致。版本查询证明安装状态，工具流程实跑另行验收。仓库只保存安装锁、包装器与说明，不保存下载二进制和第三方源码；WSL部署位置为原生 `~/asm-ws/`。

| 工具 / 资源 | 锁定或历史版本 | 接入状态 | WSL部署位置 |
|---|---|---|---|
| [dnsx](../docs/reference/dnsx.md) | 1.3.1 | 已接工作台 `dns_recursive`，逐记录/上游动作；旧Stage 5保留 | `bin/` |
| [dig](../docs/reference/dig.md) / `dns_probe.py` | dnsutils，版本未锁 | 已接工作台 `dig_probe`；旧Stage 5包装器保留 | `/usr/bin/`；包装器随任务部署 |
| [naabu](../docs/reference/naabu.md) | 2.6.1 | 已接工作台 `tcp_scan`，显式端口/分批/结果校验 | `bin/` |
| [ProjectDiscovery httpx](../docs/reference/httpx.md) | 1.12.0 | 已接 `web_visit`，通过隔离HTTP代理观察状态/标题/技术 | `bin/` |
| [ffuf](../docs/reference/ffuf.md) | 2.3.0 | 已接 `web_path_enum`，字典/随机基线/HTTP二次复核 | `bin/` |
| [katana](../docs/reference/katana.md) | 1.8.0 | 已接 `web_crawl`，精确scope/深度/请求预算 | `bin/` |
| [gowitness](../docs/reference/gowitness.md) | 3.2.0 | 已接 `screenshot`，隔离Chrome/PNG/JSONL/逐请求代理；默认gorod，原WSL真实PNG通过，chromedp本机超时 | `bin/` |
| [wafw00f](../docs/reference/wafw00f.md) | 2.4.2 | 已接 `vulnerability_check` 的明确 `waf_fingerprint` 检查 | `tools/wafw00f/.venv/` |
| [nuclei](../docs/reference/nuclei.md) | 3.11.1 | 已接 `vulnerability_check`，须批准本地GET/HEAD HTTP观察模板；不执行整库/其他协议 | `bin/` |
| [a_scan.py](../docs/reference/a_scan.md) | 仓库内 stdlib TCP扫描器 | 已接 `tcp_scan: a_scan`，显式端口/速率/分批；任务内副本，不覆盖原安装 | 原安装`tools/a_scan.py`；新版任务`results/workbench-*/a_scan.py` |
| [Google Chrome](../docs/reference/chrome.md) | 155.0.8059.39 | gowitness的浏览器依赖；当前Windows截图主流程不调用 | `/usr/bin/` |
| [SecLists](../docs/reference/seclists.md) | 2026.1，固定commit | 已接DNS、内置路径及ffuf字典输入，校验commit/blob并冻结回执；默认仍为内置字典 | `wordlists/SecLists/` |

[Amass](../docs/reference/amass.md)、[gau](../docs/reference/gau.md)、[waybackurls](../docs/reference/waybackurls.md)、[LinkFinder](../docs/reference/linkfinder.md)、[arjun](../docs/reference/arjun.md)、[x8](../docs/reference/x8.md) 只有调研专页，无当前接入/安装证据；`planned_*` 为预留适配器。它们不计入已使用工具。

每工具的场景命令、原生输出、去重核对和排错见 [reference索引](../docs/reference/README.md)。手动输出不会自动进入工作台数据库和报告。

## 4. 部署与包装器说明

八个二进制的版本、官方 URL 与 SHA-256 见 `tool-lock.json`。安装前校验下载摘要，重复安装复用已经校验的缓存。APT 包与 Chrome 版本在 WSL `manifests/installed.txt` 中记录；Python 工具各有独立 venv，兼容 Ubuntu 的 externally-managed Python。

当前复用原 `Ubuntu` 24.04 发行版；Bridge、CLI、依赖检查、配置模板及验收脚本的默认名称统一为 `Ubuntu`，显式 `WSL_DISTRO` 仍优先。已有工具齐全，不重装、不覆盖原安装；新增runner/新版a_scan随任务写入独立 `results/` 目录。仅需补装时才使用安装入口：`python -m asm init-wsl --distro <实际发行版名称>`；该入口不创建发行版。

SecLists 2026.1 文件总量约 1.96GB。默认使用固定 commit 的 partial clone 与 sparse checkout，安装版本锁指定的 raft-medium 四份 Web 字典、top-5000 DNS 字典、README 和许可证。需要其它字典时，在 WSL 原生目录扩展 sparse-checkout；安装时设置 `ASM_SECLISTS_FULL=1` 可取回完整版本。已完整检出的仓库会保留现有文件。

OneForAll 上游 requirements 的 exrex 0.10.5 与 Python 3.11+ 不兼容；bootstrap 生成有效 requirements，只将该版本替换为 0.12.0，并安装 setuptools 75.8.0 的 distutils shim。这些兼容依赖都位于 OneForAll 独立 venv，原源码及 requirements 保留。

所需字典通过官方 raw 固定 commit 地址下载，并按该 Git tree 的 blob SHA 逐一校验后写入本地 Git object store，再完成 sparse checkout。这样可复用元数据并处理 WSL 下 Git lazy-fetch 第二连接超时，不跳过哈希校验。历史部署环境自检曾18/18通过；本次未重跑该自检。

`dns_probe.py` 是 stdlib 原生 WSL dig 包装器。编排将它与 `asm/utils/dns.py`（任务内命名 dns_support.py）、targets.json 通过 stdin 写入任务目录，按指定上游查询五类记录并有界追踪 CNAME。它不从 /mnt 导入 Windows 包，不依赖 WSL dnspython，也不更改系统 resolver。dnsx 独立按每个上游执行，其观测与 dig 结果分别保留。

`oneforall_runner.py` 与 `asm/utils/oneforall.py`（任务内 oneforall_support.py）通过 stdin 写入原生任务目录，使用固定安装的独立 venv。它直接调度七来源白名单内的 Collect 和原生数据库/JSON 导出，跳过上游默认主流程的 wildcard/SRV 及父域扩张。HTTP 主机受限、重定向关闭；数据库、临时文件、模块 JSON 与日志隔离在任务目录。去重前观测保留全部来源，AlienVault 两端点在进程内合并；第三方源码不改。调用和证据细节见 RUNBOOK。

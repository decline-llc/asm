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

Stage 8 与 report 命令默认导出 xlsx、总表 report.csv、七明细 report-csv/*.csv 和自包含 report.html。HTML 内嵌可读取截图，离线/禁用 JavaScript 仍可阅读；xlsx 的截图依旧用相对链接。`report --output data/test/delivery.html` 指定共同文件名前缀，也会生成 delivery.xlsx/delivery.csv/delivery-csv/。默认阶段 8 已在 p1/p2 后，自定义阶段顺序需自行把 8 放最后。各工具的场景命令与异常处理见 [reference](reference/README.md)。

初次创建 venv 用本机已有 `D:\.pyenv\pyenv-win\versions\3.11.9\python.exe -m venv .venv`，然后 `pip install -e .[dev,browser]` 和 `python -m playwright install chromium`。不要改 pyenv 全局默认版本。

WSL apt 如被系统自动更新占锁，等待释放。若提示 dpkg interrupted，先按实际 audit 修复；不要删除锁或杀自动更新进程。网络若受 Windows loopback 代理影响，使用可达的宿主网关代理做本次命令配置，不改系统默认 DNS/防火墙。

首次远端交付使用 main，`origin=https://github.com/decline-llc/asm.git`；按用户明确要求完成推送，不覆盖远端其它人的提交。推送前 `git status`、`git diff --check`、检查 .env/data 被忽略，推送后对照 `git rev-parse HEAD` 和 `git ls-remote origin refs/heads/main`。

本机 GCM 有多个账号；仓库级 `credential.https://github.com.username=decline-llc` 已指定推送身份，凭据仍由 GCM 管理。不要把令牌写进 remote URL、配置模板或日志。

SecLists 默认按 `tools/tool-lock.json` 固定版本稀疏检出所需字典。完整安装可在 WSL 中执行 `ASM_SECLISTS_FULL=1 ASM_WS=/home/longchuanli/asm-ws bash /home/longchuanli/asm-ws/wsl-setup.sh`；其它外部工具已安装时可加 `ASM_SKIP_APT=1`。不要在未完成 clone 的目录上执行版本检查或覆盖用户改动。

Windows CLI 也可在本次调用前设置 `$env:ASM_SKIP_APT='1'` 或 `$env:ASM_SECLISTS_FULL='1'`，bootstrap 只接收 0/1 并显式传入 WSL。APT 阶段须 root；新机器执行完整安装，不跳过 APT。

Session 005（2026-10-10）重测 doctor 18/18，但系统 DNS 及显式 1.1.1.1、114.114.114.114、8.8.8.8 的 UDP/TCP 53 在 Windows/WSL 都把 `example.com` 返回为 198.18.0.122；显式上游没有避开 fake-IP。Stage 4/5 已过滤这些地址，过滤不等于取得真实地址。HTTPS DNS 对照得到公网地址，Windows 连接有波动；当前 dns.resolvers 不接受 DoH URL。先建立可信解析路径，再做实网 IP/归属核对；未修改系统 DNS/代理/防火墙。详细联网证据、API 状态、工具调用和输出说明见 [OPERATIONS.md](OPERATIONS.md)。

## OneForAll 被动收集

Stage 4 为每个范围内 DNS root 在原生 WSL 后台启动 OneForAll，同时处理 subfinder 和现有被动来源。dry-run、target-local 和 localhost 不启动它。可在 profile 设置 `oneforall.enabled: false` 关闭；省略配置时也使用以下生效默认值，它们参与恢复指纹：

```yaml
oneforall:
  enabled: true
  modules:
    - modules.certificates.certspotter
    - modules.datasets.rapiddns
    - modules.datasets.anubis
    - modules.intelligence.alienvault
    - modules.intelligence.threatminer
  module_timeout: 45
  request_timeout: 15
limits:
  oneforall_timeout: 3600
```

另外允许 `modules.certificates.crtsh` 和 `modules.datasets.hackertarget`，默认不启用以避免与现有来源重复。模块只能选这七个；不能配置目标探测、DNS、爆破、付费 API 或默认全模块。module_timeout 上限 300 秒，request_timeout 上限 60 秒。上游按线程分别 join，完整任务另受 Linux timeout 限制。

包装器核对 `tools/tool-lock.json` 固定 commit，只调用 Collect 与原生数据库/导出步骤，保留输入 root，不扩张到父域。HTTP 限定各模块的公开服务主机、GET/HEAD，关闭重定向，启用 TLS 验证，响应最多 8 MiB。RapidDNS 在这个固定版本使用 HTTP；若服务跳转或返回非 2xx，记录 partial，不跟随跳转。公网服务可达性仍需现场确认。

每任务独立保存 `vendor-results/result.sqlite3`、各模块 JSON、日志和 `oneforall.json` 原生去重输出；`oneforall-observations.json` 在去重前保存，避免上游只保留首个来源。AlienVault 的两个端点在本次进程中合并，第三方源码文件不修改。Windows 仅导入请求 root 下、全局白名单内的域名及 oneforall:来源；工具生成的 IP/80 端口等未经验证字段不入资产表，解析仍交由 Stage 5。

阶段目录 `oneforall-evidence.json` 保存 jobid、模块状态、HTTP 请求状态、接受/排除/异常记录。部分失败仍保留其余来源的有效结果，并写入 `oneforall_partial` review 待办。模块超时/HTTP 失败返回 rc=2，整任务超时 rc=124；只有完整成功且本地结果目录仍存在的相同工具/参数/输入任务可复用。需要全新采集时，使用新 profile/output 项目数据库；`--resume` 只控制阶段恢复，不关闭工具级成功缓存。

## DNS 阶段配置与证据

每个 profile 可添加以下设置；省略时使用这些默认值，最终有效值参与恢复指纹：

```yaml
dns:
  resolvers: ["1.1.1.1", "114.114.114.114", "8.8.8.8"]
  preferred_resolver: "114.114.114.114"
  timeout: 3
  workers: 8
  max_cname_hops: 16
  dnsx: true
  windows_verify: true
  reject_fake_ip: true
  takeover_probe: false
limits:
  dns_timeout: 900
```

上游支持 IP、IPv4:port、[IPv6]:port；默认端口 53，不能填 DNS 主机名或 URL。preferred_resolver 必须在列表内。测试私有 DNS 时显式配置它的地址；WSL NAT 下 Windows 与 Linux 回环不同，WSL 回环验收配置 windows_verify: false，Windows 复核另用 Windows 回环服务验证。

对于同一上游/类型，优先使用成功的 dig 观测，其次 Windows、dnsx。不同来源保留为各自记录；Windows 与 dig 不一致会留下 finding 并标 partial。A/AAAA 有优先上游可用地址时采用它，否则合并其它上游可用地址。0.0.0.0、:: 总是拒绝；198.18.0.0/15 默认拒绝，仅专门 benchmark 靶场可显式关闭 reject_fake_ip。任何错误/无结果都可追溯，未取得有效解析时 selected 为空，端口阶段和报告不会重新采用旧观测地址。实际端口目标仍必须在 IP 白名单中。

阶段目录输出 dns-observations.json（过滤前解析观测）、dns-evidence.json（按来源/上游/链组织的证据及 selected）、dns.json（可用记录）；外部工具原始文件保留在任务目录。链外部终点只用于 DNS 证据，不加入目标集合。循环、跳数耗尽、超时标 partial；悬空 NXDOMAIN 只产生候选。

takeover_probe 开启且主动授权时，才请求原始范围内域名的 HTTP(S)。命中 provider 后缀、状态码及错误文本才生成 review 项，保存 URL/状态/匹配文本/响应 SHA-256，并以 takeover_candidate 出现在报告 todos；403 私有桶不算接管。不会请求外部终点或注册资源。dry-run/target-local 继续使用隔离 fixtures，不能当成公网 DNS 验收。

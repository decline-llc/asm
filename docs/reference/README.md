# 工具 reference 索引

核对日期：2026-10-10。每个工具一页，记录固定版本、实际接入状态、场景命令、原生输出、衔接/去重/核对与异常处理；通用设置只放本页，避免多处命令漂移。命令依据本机已装版本 help 和项目代码，公网/账户验收状态另见 [ACCEPTANCE](../ACCEPTANCE.md)。

证据标记约定：**本机帮助核对**（已保存本机 `data/validation/` 下的工具 help 原文）、**回环实测**（本机 loopback 或离线 fixture 验证）、**官方文档核对**（官方文档/仓库/发行说明）、**待验证**（尚未做对应核验）。

| 分类 | 专页 |
|---|---|
| Windows 编排/报告 | [ASM Workbench](asm.md)、[Playwright](playwright.md) |
| 子域与 DNS | [subfinder](subfinder.md)、[OneForAll](oneforall.md)、[dnsx](dnsx.md)、[dig](dig.md) |
| 端口 | [nmap](nmap.md)、[masscan](masscan.md)、[naabu](naabu.md)、[a_scan](a_scan.md) |
| Web | [httpx](httpx.md)、[ffuf](ffuf.md)、[katana](katana.md)、[gowitness](gowitness.md)、[Chrome](chrome.md)、[wafw00f](wafw00f.md) |
| 模板与字典 | [nuclei](nuclei.md)、[SecLists](seclists.md) |
| 搜索 API | [通用调用/保存](api.md)、[FOFA](fofa.md)、[Quake](quake.md)、[Hunter](hunter.md)、[ZoomEye](zoomeye.md)、[Shodan](shodan.md)、[Censys](censys.md) |
| 未安装调研工具 | [Amass](amass.md)、[gau](gau.md)、[waybackurls](waybackurls.md)、[LinkFinder](linkfinder.md)、[arjun](arjun.md)、[x8](x8.md) |

## Windows / WSL 入口

Windows 命令在 PowerShell 7 Core 中执行（`pwsh.exe`，不用 Windows PowerShell 5.1）：

```powershell
Set-Location 'D:\Desktop\asm'
.\.venv\Scripts\python.exe -m asm doctor
# 进入 WSL 原生目录，然后再执行下文 Bash 命令
wsl.exe -d Ubuntu --cd /home/longchuanli/asm-ws -- bash
```

WSL 各页 Bash 命令先复制以下通用设置。占位目标须替换成项目范围内目标；历史观测中本机公共 UDP/TCP 53 曾返回 fake-IP（2026-10-10 观测，见 OPERATIONS.md 第 8 节），该状态需要复测、不能当作永久结论，RESOLVER 使用前需要独立对照验证，不能因名称是公共 DNS 就当可信。

```bash
export PATH="$HOME/asm-ws/bin:$HOME/asm-ws/tools/wafw00f/.venv/bin:$PATH"
OUT="$HOME/asm-ws/results/manual/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
ROOT='authorized.invalid'
URL='https://authorized.invalid'
IP='192.0.2.10'
RESOLVER='1.1.1.1'
WORDLIST="$HOME/asm-ws/wordlists/SecLists/Discovery/Web-Content/raft-medium-directories.txt"
printf '%s\n' "$ROOT" > "$OUT/domains.txt"
printf '%s\n' "$URL" > "$OUT/urls.txt"
printf '%s\n' "$IP" > "$OUT/ips.txt"
run_logged() {
  local name="$1"; shift
  printf '%q ' "$@" > "$OUT/$name.argv.txt"
  printf '\n' >> "$OUT/$name.argv.txt"
  "$@" > "$OUT/$name.stdout.log" 2> "$OUT/$name.stderr.log"
  local code=$?
  printf '%s\n' "$code" > "$OUT/$name.rc"
  return "$code"
}
date -u +%FT%TZ > "$OUT/started-utc.txt"
```

`run_logged` 仅用于参数不含凭据的工具命令；不要用它记录带 API Key、Cookie 或认证代理密码的 argv。API 通过 Windows `.env` 加载，见 api.md。终端 stdout 是日志或纯文本候选时，仍保留 XML/JSON/JSONL 的原生结果。

## 结果处理与异常顺序

每次人工运行独立目录，不覆盖历史结果；保存输入、版本、argv、stdout/stderr、返回码和采集时间。框架任务已自动保存在原生 `results/<jobid>/` 和 Windows `data/<profile>/results/<stage>/<jobid>/`，不用再人为搬到 /mnt。

先核对返回码和原生记录数，再查范围、fake-IP、归属、服务/页面、重复来源。返回成功且空与查询失败是两种状态；dig 的 NXDOMAIN 也可能 exit 0。人工文件没有通用自动导入入口；仅安装工具不会自动新增流水线阶段。

实网失败时依次查输入/范围 → DNS → TCP/TLS/代理 → 账户/配额 → 版本参数。根据现场证据处理，不用关闭 TLS 验证或放宽范围来掩盖失败。NAT 下两端 localhost 不相同；WSL 报 localhost 代理未镜像时，核对实际代理可达地址，不直接复制 Windows 127.0.0.1 代理端口。

维护一页时同时记录核对日期、工具版本、帮助/实测证据与接入状态。Amass、gau、waybackurls、LinkFinder、arjun、x8 目前**未安装**，其专页为调研笔记，安装核验后再更新为实操手册。

## 去重与核对总则

各工具专页引用本节通用规则，具体字段在专页内补充：

- **域名**：统一小写、去末尾点、按 IDNA 转 ASCII 后比较；`www.` 与前缀差异视为不同子域分别保留；范围按 `host == root or host.endswith("." + root)` 判定；通配符（`*.`）前缀先剥离再判定，泛解析本身不当作单个子域证据。
- **端口资产**：身份键为 `(host, port, proto)`，TCP 与 UDP 分开；域名 host 与解析出的 IP host 不强行合并（CDN/共享云场景尤其不能按 IP 吞并域名）。
- **URL**：以原始完整 URL 字符串为键；scheme、主机、端口、路径、查询参数都参与区分；不做盲目查询参数删除或语义规范化，参数可能影响语义。
- **多来源合并**：同键来源做并集（逗号分隔、排序去重）；保留各来源与首次/最近观测时间；同一底层来源经多个工具重复取得不算独立证据。
- **置信分级**：搜索结果、开放端口、指纹、模板命中是四类不同确认条件；候选线索先进入隔离或 review，不直接写成确认资产或漏洞。
- **时间戳**：数据库记录 UTC ISO 秒级时间；人工运行保存 `started-utc.txt` 与返回码。

详见 [OPERATIONS.md](../OPERATIONS.md) 第 7 节「如何去重与核对」。

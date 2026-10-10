# 工具 reference 索引

核对日期：2026-10-10。每个工具一页，记录固定版本、接入状态、场景命令、输出、核对与异常处理；通用设置只放本页，避免多处命令漂移。命令依据本机已装版本 help 和项目代码，公网/账户验收状态另见 [ACCEPTANCE](../ACCEPTANCE.md)。

| 分类 | 专页 |
|---|---|
| Windows 编排/报告 | [asm](asm.md)、[Playwright](playwright.md) |
| 子域与 DNS | [subfinder](subfinder.md)、[OneForAll](oneforall.md)、[dnsx](dnsx.md)、[dig](dig.md) |
| 端口 | [nmap](nmap.md)、[masscan](masscan.md)、[naabu](naabu.md)、[a_scan](a_scan.md) |
| Web | [httpx](httpx.md)、[ffuf](ffuf.md)、[katana](katana.md)、[gowitness](gowitness.md)、[Chrome](chrome.md)、[wafw00f](wafw00f.md) |
| 模板与字典 | [nuclei](nuclei.md)、[SecLists](seclists.md) |
| 搜索 API | [通用调用/保存](api.md)、[FOFA](fofa.md)、[Quake](quake.md)、[Hunter](hunter.md)、[ZoomEye](zoomeye.md)、[Shodan](shodan.md)、[Censys](censys.md) |

## Windows / WSL 入口

Windows 命令在 PowerShell 7 Core 中执行：

```powershell
Set-Location 'D:\Desktop\asm'
.\.venv\Scripts\python.exe -m asm doctor
# 进入 WSL 原生目录，然后再执行下文 Bash 命令
wsl.exe -d Ubuntu --cd /home/longchuanli/asm-ws -- bash
```

WSL 各页 Bash 命令先复制以下通用设置。占位目标须替换成项目范围内目标；当前 Windows/WSL 的公共 UDP/TCP 53 返回 fake-IP，RESOLVER 需要独立对照验证，不能因名称是公共 DNS 就当可信。

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

维护一页时同时记录核对日期、工具版本、帮助/实测证据与接入状态。Amass、gau、waybackurls、LinkFinder、arjun、x8 目前未安装，安装核验后再新增专页。

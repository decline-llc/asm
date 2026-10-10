# ProjectDiscovery httpx（HTTP 存活/指纹探测）

> 状态：**仅安装，尚未接入 Stage 7**（当前 Stage 7 用 Windows Python `httpx` 库，是另一组件）
> 版本：1.12.0（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/httpx`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/httpx.txt`、`web-tool-help/httpx.txt`）
> 证据：本机 `httpx -h`；当前 Web 主流程 [s7_web.py](../../asm/stages/s7_web.py)

## 1. 用途、场景与局限

- **用途**：对 URL/主机列表做 HTTP(S) 存活探测，提取状态码、标题、技术指纹、响应长度等线索。
- **适用场景**：人工对批准的 Web 目标做存活与指纹摸底；未来接入 Stage 7 前的验证。
- **局限**：**默认不跟随重定向**（`-fr`/`-fhr` 需显式开）；标题/技术是**线索**，不证明归属或漏洞。TLS/CSP 中出现的新域名只是候选，不能自动扩大范围。`-allow`/`-deny` 按 IP/CIDR 过滤解析结果——在 fake-DNS 环境下 allow 可能把目标滤掉。
- **接入状态**：已安装、未接入；原生 JSONL 不自动入库。不要与 Windows Python `httpx` 库混淆。

## 2. 实际接入状态

无自动调度。框架 Stage 7 用 Windows 侧 httpx 库（`TargetHTTP`，每跳 scope 校验、响应上限 64KiB、不自动跟随越界跳转）。WSL 二进制接入需先解决：每跳范围检查、TLS/CSP 新域名不扩权、fake-DNS 下 `-allow` 语义。

## 3. 输入准备与场景命令

> 前置：WSL、PATH 含 `~/asm-ws/bin`；`RESOLVER` 先验证可信；`-allow` 的 IP 为批准的解析地址。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 存活+指纹：保留状态、标题、技术、长度；显式上游与 IP allow
run_logged httpx httpx -l "$OUT/urls.txt" -sc -title -td -cl -j -r "$RESOLVER" -allow "$IP" -t 5 -rl 10 -duc -o "$OUT/httpx.jsonl"
# 指定 Web 端口探测域名列表
run_logged httpx-ports httpx -l "$OUT/domains.txt" -p http:80,8080,https:443 -sc -title -j -r "$RESOLVER" -allow "$IP" -rl 10 -duc -o "$OUT/httpx-ports.jsonl"
# 慢服务诊断：低并发低速长超时
run_logged httpx-slow httpx -l "$OUT/urls.txt" -sc -title -j -r "$RESOLVER" -allow "$IP" -t 2 -rl 2 -timeout 20 -duc -o "$OUT/httpx-slow.jsonl"
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 存活+指纹 | WSL | urls.txt+可信解析+批准 IP | `-l`、`-sc/-title/-td/-cl`、`-j`、`-r`、`-allow`、`-t/-rl`、`-duc` | `$OUT/httpx.jsonl` | 每 URL 一条 JSON | 全空且疑 allow 误滤；rc≠0 |
| 端口探测 | WSL | domains.txt | `-p`（nmap 语法） | `$OUT/httpx-ports.jsonl` | 端口服务记录 | 端口不通/解析失败 |
| 慢诊断 | WSL | 同上 | 低 `-t/-rl`、长 `-timeout` | `$OUT/httpx-slow.jsonl` | 对照差异 | 与正常跑一致失败→查网络 |

**参数含义**（本机 1.12.0）：`-t` 并发线程（默认 50）、`-rl` 每秒请求上限（默认 150）、`-timeout` 秒（默认 10）、`-r` 自定义解析器、`-allow/-deny` IP/CIDR 过滤、`-j` JSONL、`-duc` 关更新检查。以上命令**不开** `-fr`/`-fhr`，保持不跟随跳转。

## 4. 原生输出格式与解析

JSONL 逐行对象，常见字段：`url`、`host`、`port`、`scheme`、`status_code`、`title`、`tech`、`content_length`、`webserver`、`final_url`（若跟随）。脱敏样例：

```json
{"url":"https://authorized.invalid","host":"authorized.invalid","port":443,"scheme":"https","status_code":200,"title":"Portal","tech":["nginx"],"content_length":1523,"webserver":"nginx"}
```

**解析方法**：逐行 `json.loads`；按 `url` 与 `host/port/proto` 建关系；`title`/`tech` 作线索。`-td` 的技术基于 wappalyzer 数据集。

## 5. 结果衔接与入库

- 衔接：存活 URL/服务 → katana/ffuf（路径与爬取）→ gowitness/Playwright（截图）。
- 入库：**当前不自动入库**；接入 Stage 7 前需补范围控制适配器。
- 403/502 等状态保存状态+长度，结合基线判断，不单独判定泄露。

## 6. 去重、来源与复核

- 去重键：完整 URL（含 scheme/host/port/path）；host 维度另按 `(host,port,proto)` 归并。
- 来源保留：JSONL 自带 url/host；人工运行保存 argv/rc/时间。
- 时间戳：保存 `started-utc.txt` 与 rc。
- 独立复核：用 `-mc`/`-fc` 对照、与 Stage 7 Windows httpx 结果交叉；allow 过滤后零结果要核对真实解析 IP。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| allow 后零结果 | 检查真实解析 IP；fake-IP 会被 allow 排除 |
| 403/502 | 保存状态、长度与基线；不判定存在泄露 |
| TLS 失败 | 区分证书、握手超时、代理；核对可信路径 |
| 重定向到外部 | 保存 Location 作 review；接入需每跳范围检查 |
| 速率被限制 | 降 `-rl`/`-t`；必要时 `-rlm` 按分钟限速 |
| 版本参数差异 | 以本机 `httpx -h`（1.12.0）为准；`-timeout` 是秒整数 |

## 8. 官方来源与核对记录

- 官方仓库核对：[projectdiscovery/httpx](https://github.com/projectdiscovery/httpx)；版本 1.12.0 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`httpx -h` 原文 `data/validation/reference-help/httpx.txt` 与 `data/validation/web-tool-help/httpx.txt`；Windows 侧对照 [asm/utils/http.py](../../asm/utils/http.py)。
- 待验证：接入 Stage 7 的范围控制适配器（每跳校验）；fake-DNS 下 `-allow` 的可用性；与 Windows httpx 库结果的一致性。

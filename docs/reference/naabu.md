# naabu（端口发现）

> 状态：**仅安装，尚未接入自动调度**
> 版本：2.6.1（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/naabu`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/naabu.txt`）
> 证据：本机 `naabu -h`

## 1. 用途、场景与局限

- **用途**：快速发现主机开放端口（候选），作为 nmap 之外的端口探测补充。
- **适用场景**：人工对批准 IP 做端口候选复核；未来可作为适配器接入。
- **局限**：**只产端口观测，不含充分服务/版本证据**；选出的端口仍需交 nmap `-sV`。`-verify` 是 TCP 复核，**不表示**组织归属已验证。SYN 扫描需要 raw socket 权限；`-s c`（CONNECT）无需特权但语义不同。
- **接入状态**：已安装、**未接入**任何 Stage；原生 JSONL 不自动入库。放入 `results/` 不会进数据库（不是文件名错误，是没有适配器）。

## 2. 实际接入状态

无自动调度。人工调用自存 JSONL，需人工或未来适配器把候选交 nmap。使用 IP 输入可减少本机 fake-DNS 的干扰，但 IP 仍须属于批准范围。

## 3. 输入准备与场景命令

> 前置：WSL、PATH 含 `~/asm-ws/bin`；目标为批准 IP。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# CONNECT 无需原始包权限，复核开放端口
run_logged naabu naabu -host "$IP" -p 80,443 -s c -verify -rate 100 -duc -j -o "$OUT/naabu.jsonl"
# 批量具体批准 IP，控制速率
run_logged naabu-batch naabu -l "$OUT/ips.txt" -p 80,443,8080 -s c -verify -rate 50 -duc -j -o "$OUT/naabu-batch.jsonl"
# 查看本机帮助
run_logged naabu-help naabu -h
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 单 IP CONNECT | WSL 用户 | 批准 IP | `-host`、`-p`、`-s c`、`-verify`、`-rate`、`-duc`、`-j`、`-o` | `$OUT/naabu.jsonl` | 开放端口 JSONL | rc≠0；raw socket 报错（改用 `-s c`） |
| 批量 | WSL 用户 | `ips.txt` | `-l` 文件 | `$OUT/naabu-batch.jsonl` | 每 IP 候选 | 速率过高丢包；降 `-rate` |
| `-h` | 任意 | — | — | stdout 文本 | 打印帮助 | — |

## 4. 原生输出格式与解析

JSONL（`-j`）逐行对象，关键字段 `host`、`ip`、`port`、`protocol`。脱敏样例：

```json
{"host":"203.0.113.10","ip":"203.0.113.10","port":443,"protocol":"tcp"}
```

**解析方法**：逐行 `json.loads`；键 `(host/ip, port, protocol)`。这是**候选**，不是服务确认。终端文本输出（非 `-j`）按 `host:port` 行解析，不如 JSONL 可靠。

## 5. 结果衔接与入库

- 衔接：naabu 候选 → nmap `-sV` 服务确认 → （未来适配器）入库。
- 入库：**当前不入库**；需新增适配器并经范围过滤后才可能接入。
- 确认失败的候选只作线索，不当存活 Web。

## 6. 去重、来源与复核

- 去重键：`(host, port, proto)`；与 masscan/nmap 候选合并时保留来源。
- 来源保留：JSONL 自带 host/ip；人工运行保存 argv/stdout/rc。
- 时间戳：保存 `started-utc.txt` 与 rc。
- 独立复核：对同一 IP，naabu 候选与 nmap 结果对照，差异查速率/丢包/权限。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| raw socket 错误 | 用 `-s c`（CONNECT）或按批准配置 root；不随意换扫描范围 |
| 结果不稳定/丢包 | 降 `-rate`、检查超时与丢包，对照 nmap |
| 结果放入 results 没入库 | 当前无自动适配器，属预期 |
| SYN 权限不足 | 非 root 用 `-s c` |
| 域名输入得 fake-IP | 改用批准的可信具体 IP；先修复解析路径 |
| 版本参数差异 | 以本机 `naabu -h`（2.6.1）为准 |

## 8. 官方来源与核对记录

- 官方仓库核对：[projectdiscovery/naabu](https://github.com/projectdiscovery/naabu)；版本 2.6.1 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`naabu -h` 原文 `data/validation/reference-help/naabu.txt`。
- 待验证：服务复核与适配器接入；SYN 模式在 WSL 的实测；与 nmap 的一致性基线。

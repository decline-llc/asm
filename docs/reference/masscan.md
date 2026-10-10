# masscan（高速端口候选）

> 状态：**可选引擎，已接入调度**（`ports.engine: masscan`；完整实际扫描验收待补）
> 版本：1.3.2（WSL apt）
> 位置：WSL `/usr/bin/masscan`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/masscan.txt`，注意该版本 help/version 退出码为 1）
> 证据：本机 `--help/--echo`、调度代码 [s6_port.py](../../asm/stages/s6_port.py)

## 1. 用途、场景与局限

- **用途**：对大端口范围做高速 SYN 探测，快速圈出开放端口**候选**，再交给 nmap 做服务确认。
- **适用场景**：Stage 6 选择 `ports.engine: masscan` 时的第一段；人工对批准 IP 做快速端口面摸底。
- **局限**：**只产候选、不识别服务**——后续 nmap `-sV` 不可省略。速率过高会丢包/被限速；raw socket 在 WSL NAT 下的可用性需先验证。固定版本的 `--help`/`--version` 退出码为 1（已知特殊响应），不能据此判失败。
- **接入状态**：Stage 6 可选引擎；候选开放端口经 nmap 确认后才入 `assets`。人工 JSON 不自动入库。

## 2. 实际接入状态

Stage 6 调用（root，后台）：`masscan <target> -p<ports> --rate <rates.masscan_rate|1000> -oJ {job}/masscan.json`。解析只取 `proto=="tcp"` 的开放端口，若有候选则再起一次 nmap（`-sS -sCV`）确认服务；`honeypot` 判定（请求端口 ≥1000 全开）会跳过后续。蜜罐/空候选直接跳过，不生成资产。

## 3. 输入准备与场景命令

> 前置：WSL、root（raw socket）；目标为批准 IP。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 基础候选扫描（速率按网络调整）
run_logged masscan sudo masscan "$IP" -p80,443 --rate 1000 -oJ "$OUT/masscan.json"
# 网络丢包/限速场景先降低发送速率
run_logged masscan-slow sudo masscan "$IP" -p80,443 --rate 100 -oJ "$OUT/masscan-slow.json"
# 只输出最终生效配置，不扫描（核对参数用）
run_logged masscan-config masscan "$IP" -p80,443 --rate 100 --echo
# 候选开放后，用 nmap 核对具体服务
run_logged masscan-verify nmap -sT -sV -Pn -n -p 80,443 -oX "$OUT/masscan-verify.xml" "$IP"
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| `masscan IP -p… --rate … -oJ` | root | 批准 IP | `-p` 端口、`--rate` 每秒包数、`-oJ` JSON | `$OUT/masscan.json` | 开放端口记录 | rc≠0 且 stderr 非已知 help 码；JSON 为空且疑丢包 |
| `--echo` | 任意 | — | `--echo` 仅回显配置 | stdout 文本 | 打印配置 | 参数拼写错误 |
| `nmap -sV` 复核 | WSL | 已有候选 | `-sV` 服务 | `$OUT/masscan-verify.xml` | 服务确认 | 无服务→保留候选待查 |

**不要在 WSL 扫不到时随意添加 adapter/router 参数**；先保存接口、网关与网络证据，确认 NAT/raw socket 能力后再配置。主流程速率由 `rates.masscan_rate` 控制。

## 4. 原生输出格式与解析

JSON（`-oJ`）是数组，元素含 `ip`、`ports`（每项 `port`、`proto`、`status`）。脱敏样例：

```json
[{"ip":"203.0.113.10","ports":[{"port":80,"proto":"tcp","status":"open"}]},
 {"ip":"203.0.113.10","ports":[{"port":443,"proto":"tcp","status":"open"}]}]
```

**解析方法**：`json.load` 读数组；展平为 `(ip, port, proto)`；只取 `status=="open"`。框架只消费 TCP 候选。

## 5. 结果衔接与入库

- 衔接：masscan 候选 → nmap `-sV` 确认服务 → `assets`。
- 入库：**只有经 nmap 确认的服务端口**才入 `assets`（source 标 nmap 侧）；masscan 本身的候选不直接入库。
- 确认失败的候选保留为 review/线索，不把 SYN 候选当存活 Web。

## 6. 去重、来源与复核

- 去重键：`(ip, port, proto)`（TCP/UDP 分开）。
- 来源保留：masscan 结果文件与 nmap XML 同任务目录留存，便于对照。
- 时间戳：任务 `job.log`/rc 与文件时间。
- 独立复核：`--echo` 核配置；同一目标 masscan 候选数与 nmap 确认数对照，差异即丢包/过滤线索。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| help/version 返回 rc=1 | 该固定版本已知行为，不是失败；以实际扫描 stderr 为准 |
| 扫描结果为空 | 检查速率、raw socket 能力、目标是否在线；降速重跑 |
| WSL 下无响应 | 核对 NAT/raw socket；不要盲加 adapter/router，先存网络证据 |
| 全端口都开 | 可能蜜罐/中间设备；对照 nmap，框架按 honeypot 跳过 |
| 丢包导致漏报 | 降 `--rate`、分端口段重跑并合并 |

## 8. 官方来源与核对记录

- 官方仓库核对：[robertdavidgraham/masscan](https://github.com/robertdavidgraham/masscan)；选项以本机 `--help/--echo` 为准。
- 本机证据：`data/validation/reference-help/masscan.txt`；调度 [s6_port.py](../../asm/stages/s6_port.py)（含 honeypot 与 nmap 复核逻辑）。
- 待验证：完整实际扫描验收（Stage 6 masscan 引擎的实网/回环一致性）；WSL raw socket 实测基线。

# a_scan.py（项目内置 TCP connect 备用扫描）

> 状态：**仅安装（项目脚本，已部署并通过 help 自检），未自动调度**
> 版本：随仓库（无独立版本号；stdlib 实现）
> 位置：WSL `~/asm-ws/tools/a_scan.py`（源码 [tools/scanners/a_scan.py](../../tools/scanners/a_scan.py)）
> 核对日期：2026-10-10（源码核对）
> 证据：项目源码

## 1. 用途、场景与局限

- **用途**：Python 标准库实现的 TCP connect 备用端口扫描器，用于在没有 nmap/masscan/naabu 或只需快速连通性判断时圈定开放端口候选。
- **适用场景**：最小依赖的端口连通性验证；作为其它扫描器失效时的兜底。
- **局限**：**只输出成功 connect 的端口**，`service` 恒为 `unknown`，**不做服务/版本识别**，**不扫描 UDP**。connect 成功只证明 TCP 可达，不证明服务身份或归属。输入应是批准的**具体 IP**——给域名会受本机 fake-DNS 影响。
- **接入状态**：已部署、help 通过；**未接入**主流水线；stdout JSONL 不自动入库。

## 2. 实际接入状态

独立脚本，无 Stage 调用。线程池（`--threads`）对每个端口做 `socket.create_connection`，成功即打印一行 JSON 到 stdout。无任何网络库依赖，适合精简环境。

## 3. 输入准备与场景命令

> 前置：WSL、`python3`（stdlib 即可）；目标为批准 IP。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 基础：少量端口，短超时，适度并发
run_logged a_scan python3 "$HOME/asm-ws/tools/a_scan.py" --host "$IP" --ports 80,443 --timeout 1 --threads 8
# 较慢网络：延长连接超时、降低线程数
run_logged a_scan-slow python3 "$HOME/asm-ws/tools/a_scan.py" --host "$IP" --ports 8000-8010,8443 --timeout 3 --threads 4
# 查看帮助
run_logged a_scan-help python3 "$HOME/asm-ws/tools/a_scan.py" --help
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 基础 | WSL | 批准 IP | `--host`、`--ports`（逗号/范围）、`--timeout` 秒、`--threads` | stdout 每行 JSON → `$OUT/a_scan.stdout.log` | 开放端口行 | rc≠0；端口范围非法会 `parser.error`（rc=2） |
| 慢网 | WSL | 同上 | 更大 timeout、更小 threads | `$OUT/a_scan-slow.stdout.log` | 连通端口 | stdout 空且疑超时→查目标/超时 |
| `--help` | 任意 | — | — | stdout 文本 | 打印用法 | — |

**参数含义**：`--ports` 支持 `80,443` 与 `8000-8010` 混合；`--timeout` 是每次 connect 秒数（默认 1）；`--threads` 并发上限（默认 64）。默认端口集 `80,443,3000,8000,8080,8443,9090,9200`。

## 4. 原生输出格式与解析

stdout 每行一个 JSON 对象（JSONL）：`host`、`port`、`proto`（恒 `tcp`）、`service`（恒 `unknown`）。样例：

```json
{"host": "203.0.113.10", "port": 443, "proto": "tcp", "service": "unknown"}
```

**解析方法**：检查 rc 后可把 stdout.log 当作 `.jsonl` 逐行 `json.loads`。空输出表示没有成功 connect（不是“无服务”的最终结论，需结合超时/网络判断）。

## 5. 结果衔接与入库

- 衔接：connect 成功的端口候选 → nmap `-sV` 服务识别。
- 入库：**不自动入库**；人工结果文件不会被 ASM 导入。

## 6. 去重、来源与复核

- 去重键：`(host, port, proto=tcp)`。
- 来源保留：stdout.log 即原始记录；保存 argv/rc/`started-utc.txt`。
- 时间戳：`started-utc.txt` 与 rc 文件。
- 独立复核：与 nmap `-sT` 对同一批准 IP 的结果对照。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| stdout 为空 | 可能无成功连接；核对目标、超时与 stderr，不断言无服务 |
| 扫描慢 | 按目标负载调 `--threads`/`--timeout` |
| 域名解析为 fake-IP | 改用批准的可信具体 IP；先修复解析路径 |
| 端口参数非法 | 范围须 `1-65535`；非法输入 rc=2 |
| 需要服务识别 | 交 nmap；a_scan 不提供 |

## 8. 官方来源与核对记录

- 依据：项目源码 [tools/scanners/a_scan.py](../../tools/scanners/a_scan.py)（stdlib，无上游版本）。
- 本机证据：部署清单 WSL `manifests/installed.txt`；help 自检通过（见 ACCEPTANCE 工具部署）。
- 待验证：与 nmap 的一致性基线；是否值得纳入适配器。

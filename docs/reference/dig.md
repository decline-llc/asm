# dig（DNS 查询，dnsutils）

> 状态：**已自动调用**（Stage 5 经原生包装器 `tools/dns_probe.py`）
> 版本：dnsutils（WSL apt 安装；版本以 `manifests/installed.txt` 记录为准）
> 位置：WSL `/usr/bin/dig`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/dig.txt`；回环实测：本地回环 DNS 服务通过，见 ACCEPTANCE）
> 证据：本机 `dig -h`、包装器 [tools/dns_probe.py](../../tools/dns_probe.py)、解析 [asm/utils/dns.py](../../asm/utils/dns.py)

## 1. 用途、场景与局限

- **用途**：对指定上游做精确 DNS 查询，是 Stage 5 的首选观测来源（同上游优先级 dig → Windows → dnsx）。
- **适用场景**：单记录核对（A/AAAA/MX/NS/CNAME）、UDP/TCP 传输对照、非标准端口自有解析器验证、CNAME 链追踪。
- **局限**：人工 dig 输出是**文本**，需要保留完整 SERVER/status/ANSWER 段；`+short` 只适合快速看值、不能作归属证据。dig 的 **NXDOMAIN 也可能 exit 0**（退出码不表示有记录）。SERVER 字段显示的是指定地址，**不证明**网络路径未被代理/TUN 拦截——这是历史 fake-IP 问题的关键陷阱。
- **接入状态**：Stage 5 用 stdlib 包装器 `dns_probe.py` 在原生 WSL 调 dig，输出 `dig.jsonl`；人工调用结果不自动入库。

## 2. 实际接入状态

包装器调用形态：`dig @<host> -p <port> <domain>. <rtype> +noall +answer +comments +time=<timeout> +tries=1`，逐 rtype（A/AAAA/MX/NS/CNAME）查询并有界追踪 CNAME 链（默认 `max_hops=16`），输出每行一个 JSON 观测到 `dig.jsonl`。链外终点只作证据、不加入目标集合。包装器只依赖 stdlib，不从 `/mnt` 导入 Windows 包，也不改系统 resolver。

## 3. 输入准备与场景命令

> 前置：WSL、`RESOLVER` 先经独立对照验证可信。通用变量/`run_logged` 见 [索引](README.md)。人工 dig 用 run_logged 保存完整文本到 stdout.log。

```bash
run_logged dig-a dig @"$RESOLVER" "$ROOT" A +time=3 +tries=1
run_logged dig-aaaa dig @"$RESOLVER" "$ROOT" AAAA +time=3 +tries=1
run_logged dig-cname dig @"$RESOLVER" "$ROOT" CNAME +time=3 +tries=1
run_logged dig-ns dig @"$RESOLVER" "$ROOT" NS +time=3 +tries=1
run_logged dig-mx dig @"$RESOLVER" "$ROOT" MX +time=3 +tries=1
# UDP/TCP 传输对照（判断传输层是否被分别拦截）
run_logged dig-tcp dig @"$RESOLVER" "$ROOT" A +tcp +time=3 +tries=1
# 自有解析服务器的非标准端口
run_logged dig-custom dig @"$RESOLVER" -p 5353 "$ROOT" A +time=3 +tries=1
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| `dig @R ROOT A` | WSL | 可信上游 | `@`上游、`A`、`+time`、`+tries` | stdout 文本 | status NOERROR + ANSWER | status SERVFAIL/超时/无 ANSWER 且 status≠NXDOMAIN |
| `+tcp` | WSL | 同上 | `+tcp` 走 TCP 53 | stdout 文本 | 与 UDP 一致 | TCP 失败而 UDP 成功 → 传输差异 |
| `-p 5353` | WSL | 自有解析器 | `-p` 端口 | stdout 文本 | 自定义端口响应 | 连接被拒/超时 |

## 4. 原生输出格式与解析

完整文本（保留证据用）：

```text
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 12345
;; QUESTION SECTION:
;authorized.invalid.		IN	A
;; ANSWER SECTION:
authorized.invalid.	300	IN	A	203.0.113.10
;; SERVER: 1.1.1.1#53(1.1.1.1)
```

**关键字段**：`status:`（NOERROR/NXDOMAIN/SERVFAIL…）、ANSWER 段（name/TTL/IN/rtype/value）、`SERVER`（实际应答的上游与端口）。**解析方法**：人工核对时读全文；程序化时项目用 `parse_dig()` 正则抽 status 与五字段 answer 行。`+short` 只返回值、丢失 status/SERVER，不能替代完整证据。

## 5. 结果衔接与入库

- 衔接：dig 观测 → Stage 5 ingest（record_value 过滤 fake-IP、CNAME 链、CDN 指纹）→ selected。
- 入库：经 Stage 5 入 `dns_records`，`resolver` 记为 `dig@<上游>`；CNAME 链存 facts `dns:<domain>` 的 `chains`。
- 悬空 CNAME（链终点 NXDOMAIN）只生成 `dangling_cname_candidate` review，**不**直接判定可接管。

## 6. 去重、来源与复核

- 去重键：`(domain, rtype, value, resolver)`。
- 来源保留：`dig@<上游>` 与 `dnsx@`、`windows@` 区分；同上游三来源分歧会留 `dns_verification_mismatch`。
- 时间戳：入库 `ts`；人工保存 `started-utc.txt` 与 rc。
- 独立复核：同一域名对比 UDP/TCP、对比 dig/dnsx/Windows、对照 DoH；链状态看 `dns-evidence.json` 的 `chains[*].status`（complete/nxdomain/loop/max_hops/error/invalid）。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| UDP 不通/TCP 可用 | 分别存证据；核对防火墙/解析器策略是否只拦 UDP |
| 两种传输都 fake-IP | 先修复解析路径；换工具不会恢复真实地址 |
| NXDOMAIN 但 exit 0 | dig 正常行为；以 status 字段为准，不以退出码判有记录 |
| 悬空 CNAME | 留 review；仅 NXDOMAIN 不证明可接管 |
| 环路/长链 | 看 Stage 5 chain status 与 max_hops 上限，不无限追踪 |
| SERVER 显示指定地址 | 不证明路径未被拦截；需 DoH/独立路径对照 |

## 8. 官方来源与核对记录

- 官方文档核对：dig 属 ISC BIND dnsutils；选项以本机 `dig -h` 原文 `data/validation/reference-help/dig.txt` 为准（含 `+https`/`+tls` 等 DoH/DoT 选项，但当前项目未用）。
- 本机证据：[tools/dns_probe.py](../../tools/dns_probe.py)、[asm/utils/dns.py](../../asm/utils/dns.py)（`parse_dig`、`record_value` fake-IP 过滤）；离线证据 `data/validation/dns/multi-resolver/` 与 `negative-cases/`。
- 待验证：可信解析路径建立后的实网一致性；DoH/DoT 作为可信上游的适配（当前配置只接受 IP/IP:port）。

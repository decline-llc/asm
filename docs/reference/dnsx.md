# dnsx（DNS 记录探测）

> 状态：**已自动调用**（Stage 5，按每个配置上游独立运行）
> 版本：1.3.1（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/dnsx`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/dnsx.txt`；回环实测：本地多解析商 fixture 通过，见 ACCEPTANCE）
> 证据：本机 `dnsx -h`、调度代码 [s5_dns_cdn.py](../../asm/stages/s5_dns_cdn.py)

## 1. 用途、场景与局限

- **用途**：对域名列表批量查询 A/AAAA/MX/NS/CNAME 等记录，作为 dig 之外的第二个解析观测来源。
- **适用场景**：Stage 5 多上游 DNS 观测、按解析商保留差异、生成 selected 可用地址的输入之一。
- **局限**：只做解析，不做端口/服务判定；**结果可信性取决于上游**——历史上本机显式公共上游（1.1.1.1/114.114.114.114/8.8.8.8 的 UDP/TCP 53）曾把 `example.com` 返回为 fake-IP `198.18.0.122`（2026-10-10 观测，需复测，非永久结论）。dnsx 本身不识别 fake-IP，过滤在 Stage 5 `record_value(reject_fake_ip=True)`。`-wd` 通配符模式会忽略其它部分 flag，应单独运行。
- **接入状态**：Stage 5 对每个 `dns.resolvers` 上游分别后台调用一次；人工原生 JSONL 不自动入库。

## 2. 实际接入状态与解析优先级

框架调用（每上游一次）：`dnsx -l {job}/domains.txt -a -aaaa -mx -ns -cname -j -silent -nc -duc -retry 1 -t <workers> -rl 60 -timeout <timeout>s -r <resolver> -o {job}/dnsx.jsonl`。同一上游多来源的选择优先级是 **dig → Windows → dnsx**；dnsx 观测与 dig 分别保留，不合并成“最终 IP”。解析出 `0.0.0.0`、`::`、默认 `198.18.0.0/15` 的记录会被拒绝（可专门 benchmark 时显式关闭）。

## 3. 输入准备与场景命令

> 前置：WSL、PATH 含 `~/asm-ws/bin`；`RESOLVER` 必须先经独立对照（如 DoH）验证可信。通用变量/`run_logged` 见 [索引](README.md)。

### 3.1 单上游五类记录（框架同款）

```bash
run_logged dnsx dnsx -l "$OUT/domains.txt" -a -aaaa -mx -ns -cname -j -silent -nc -duc -retry 1 -t 8 -rl 60 -timeout 3s -r "$RESOLVER" -o "$OUT/dnsx.jsonl"
```

- 参数：`-l` 域名列表；`-a/-aaaa/-mx/-ns/-cname` 记录类型；`-j` JSONL 输出；`-silent` 只出结果；`-nc` 去颜色；`-duc` 关更新检查；`-retry` 重试次数；`-t` 并发线程；`-rl` 每秒请求上限；`-timeout` 单查询超时；`-r` 指定上游；`-o` 输出文件。
- 输出：`$OUT/dnsx.jsonl`；rc 文件。
- 预期：exit 0，逐行 JSON。
- 失败判定：rc≠0、stderr 报错、行数为零且 status 全为非 NOERROR。

### 3.2 低并发低速诊断（对照用）

```bash
run_logged dnsx-slow dnsx -l "$OUT/domains.txt" -a -aaaa -j -duc -t 2 -rl 5 -retry 1 -timeout 5s -r "$RESOLVER" -o "$OUT/dnsx-slow.jsonl"
```

- 用途：排除速率/并发导致的丢包或上游限速；与正常跑分文件对照，差异即线索。

### 3.3 通配符诊断（独立任务）

```bash
run_logged dnsx-wildcard dnsx -l "$OUT/domains.txt" -wd "$ROOT" -j -duc -r "$RESOLVER" -o "$OUT/dnsx-wildcard.jsonl"
```

- 注意：`-wd` 与其余查询 flag 互斥（官方说明“other flags will be ignored”），需单独运行并建议 JSON 输出。
- 用途：判断 root 是否泛解析，避免把泛解析地址当真实资产。

## 4. 原生输出格式与解析

JSONL 逐行一个对象。关键字段：`host`（查询名）、各记录类型字段（`a`/`aaaa`/`mx`/`ns`/`cname`，值为数组）、`status_code`、`resolver`（若指定）。脱敏样例：

```json
{"host":"api.authorized.invalid","a":["203.0.113.10"],"aaaa":[],"cname":[],"status_code":"NOERROR","resolver":"1.1.1.1"}
{"host":"mail.authorized.invalid","a":[],"mx":["10 mail.authorized.invalid"],"status_code":"NOERROR"}
```

**解析方法**：逐行 `json.loads`（不是整体数组）；保留 `resolver`、记录类型、值与采集时间；`status_code` 缺省且无任何 answer 时按 `NOANSWER` 处理（框架 parse_dnsx 逻辑）。**不要把多个上游的输出混在一起只留“最终去重 IP”**——会丢失解析商差异证据。

## 5. 结果衔接与入库

- 衔接：dnsx 观测 → Stage 5 ingest（record_value 过滤、CNAME 链、CDN 指纹）→ selected 地址 → Stage 6 端口。
- 入库：经 Stage 5 入库 `dns_records`（键 `(domain,rtype,value,resolver)`），`resolver` 记录为 `dnsx@<上游>`；人工 JSONL 不自动入库。
- fake-IP 与 `0.0.0.0`/`::` 在入库前被拒绝并留 `rejected` 证据与 `dns_unusable_answer` review。

## 6. 去重、来源与复核

- 去重键：`(domain, rtype, value, resolver)`；同一域名在不同上游的记录**分别保留**。
- 来源保留：`resolver` 字段带 `dnsx@<上游>` 前缀，与 `dig@`、`windows@` 区分。
- 时间戳：入库记录 `ts`（UTC 秒）；人工运行保存 `started-utc.txt` 与 rc。
- 独立复核：对同一域名分别看 dig/dnsx/Windows 三来源是否一致；`dns-evidence.json` 的 `source_differences`、`windows_verification` 字段即为此设。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 三家上游都返回 198.18/15 | 对照 HTTPS DNS/解析路径；一致不证明三份独立证据（可能同一拦截路径） |
| 无记录/超时 | 查 stderr、`-rl`/`-t`、DNS status code；不要回退旧地址 |
| 通配符过滤过多 | 独立保留通配符任务与普通解析，人工核对 `-wt` 阈值 |
| 速率被上游限制 | 降 `-rl`、增 `-retry`、换可信上游；与 dig 结果对照 |
| 版本参数差异 | 以本机 `dnsx -h`（1.3.1）为准；`-timeout` 是时长值（如 `3s`）非秒数整数 |
| `-wd` 忽略其它 flag | 官方设计；单独运行通配符诊断 |

## 8. 官方来源与核对记录

- 官方仓库核对：[projectdiscovery/dnsx](https://github.com/projectdiscovery/dnsx)；版本 1.3.1 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`dnsx -h` 原文 `data/validation/reference-help/dnsx.txt`；调度参数见 [s5_dns_cdn.py](../../asm/stages/s5_dns_cdn.py)；多解析商离线证据 `data/validation/dns/multi-resolver/`。
- 待验证：可信解析路径建立后的实网多上游一致性；DoH 适配器（当前 `dns.resolvers` 只接受 IP/IP:port，不支持 DoH URL）。

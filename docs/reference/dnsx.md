# dnsx

固定 1.3.1，Stage 5 已接入。以下是原生 Bash；RESOLVER 必须先验证可信，当前本机公共 53 仍返回 fake-IP。

```bash
# 单上游五类记录，保留原始 DNS 详情
run_logged dnsx dnsx -l "$OUT/domains.txt" -a -aaaa -mx -ns -cname -j -silent -nc -duc -retry 1 -t 8 -rl 60 -timeout 3s -r "$RESOLVER" -o "$OUT/dnsx.jsonl"
# 低并发/低速诊断，用不同输出文件保持对照
run_logged dnsx-slow dnsx -l "$OUT/domains.txt" -a -aaaa -j -duc -t 2 -rl 5 -retry 1 -timeout 5s -r "$RESOLVER" -o "$OUT/dnsx-slow.jsonl"
# 通配符诊断另开任务；-wd 模式会忽略其它部分 flags
run_logged dnsx-wildcard dnsx -l "$OUT/domains.txt" -wd "$ROOT" -j -duc -r "$RESOLVER" -o "$OUT/dnsx-wildcard.jsonl"
```

JSONL 逐行解析，保留 resolver、type、value 和采集时间；不能把多个上游放一起后只保留“最终去重 IP”，否则丢失差异。Stage 5 同上游优先 dig→Windows→dnsx，selected 才交端口/报告。

| 情况 | 处理 |
|---|---|
| 三家都返回 198.18/15 | 对照 HTTPS DNS/解析路径；一致不证明三份独立证据 |
| 无记录/超时 | 查 stderr、请求速率、DNS response code；不要回退旧地址 |
| 通配符过滤过多 | 独立保留通配符任务与普通解析，再人工核对 |

依据：本机 dnsx -h，[Stage 5](../../asm/stages/s5_dns_cdn.py)。

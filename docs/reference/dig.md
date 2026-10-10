# dig

WSL dnsutils 已安装。Stage 5 通过原生包装器生成 dig.jsonl；人工 dig 输出是文本，见 stdout.log。

```bash
run_logged dig-a dig @"$RESOLVER" "$ROOT" A +time=3 +tries=1
run_logged dig-aaaa dig @"$RESOLVER" "$ROOT" AAAA +time=3 +tries=1
run_logged dig-cname dig @"$RESOLVER" "$ROOT" CNAME +time=3 +tries=1
run_logged dig-ns dig @"$RESOLVER" "$ROOT" NS +time=3 +tries=1
run_logged dig-mx dig @"$RESOLVER" "$ROOT" MX +time=3 +tries=1
# UDP/TCP 传输对照
run_logged dig-tcp dig @"$RESOLVER" "$ROOT" A +tcp +time=3 +tries=1
# 自有解析服务器的非标准端口
run_logged dig-custom dig @"$RESOLVER" -p 5353 "$ROOT" A +time=3 +tries=1
```

保留完整 SERVER、status、QUESTION、ANSWER，+short 只适合快速看值，不能替代归属证据。NXDOMAIN 可能 exit 0；SERVER 字段显示指定地址，也不证明网络路径未被代理拦截。CNAME 外部终点是证据，不自动加入主动目标。

| 情况 | 处理 |
|---|---|
| UDP 不通/TCP 可用 | 分别存证据，核对防火墙/解析器策略 |
| 两种传输都 fake-IP | 先修复解析路径，改变工具不会恢复地址 |
| 悬空 CNAME | 留 review；仅 NXDOMAIN 不证明可接管 |
| 环路/长链 | 看 Stage 5 chain status/hop 上限，不无限追踪 |

依据：本机 dig -h，[dns_probe.py](../../tools/dns_probe.py)。

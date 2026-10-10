# naabu

固定 2.6.1，已安装、尚未接入自动调度。以下原生 JSONL 不会自动入库。

```bash
# CONNECT 无需原始包权限，复核开放端口
run_logged naabu naabu -host "$IP" -p 80,443 -s c -verify -rate 100 -duc -j -o "$OUT/naabu.jsonl"
# 批量具体批准 IP，控制速率
run_logged naabu-batch naabu -l "$OUT/ips.txt" -p 80,443,8080 -s c -verify -rate 50 -duc -j -o "$OUT/naabu-batch.jsonl"
run_logged naabu-help naabu -h
```

JSONL 是端口观测，不含充分服务/版本证据；选出的端口交 nmap -sV。-verify 表示 TCP 复核，不表示组织归属已验证。使用 IP 输入可以减少本机假 DNS 的干扰，但 IP 仍须属于批准范围。

| 情况 | 处理 |
|---|---|
| raw socket 错误 | 用 -s c 或按批准配置 root；不随意更换扫描范围 |
| 结果不稳定 | 降速、检查超时/丢包，对照 nmap |
| 放 results 没入库 | 当前未有自动适配器，不是文件名错误 |

依据：本机 naabu -h（data/validation/reference-help/naabu.txt）。

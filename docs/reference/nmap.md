# nmap

WSL 7.94SVN，Stage 6 默认引擎；真实回环 TCP/UDP 已验收。Bash 示例只用于批准的具体 IP。

```bash
# 少量服务端口，XML 保留服务证据
run_logged nmap nmap -sT -sV -Pn -n -p 80,443 -oX "$OUT/nmap.xml" "$IP"
# 框架使用 root SYN + 服务/默认脚本识别
run_logged nmap-syn sudo nmap -sS -sV -sC -Pn -n -p 80,443 -oX "$OUT/nmap-syn.xml" "$IP"
# 选定 UDP 服务，不能把 UDP open|filtered 当确定开放
run_logged nmap-udp sudo nmap -sU -sV -Pn -n -p 53,123 -oX "$OUT/nmap-udp.xml" "$IP"
# 批准主机的全 TCP 端口，另存结果
run_logged nmap-full sudo nmap -sS -sV -Pn -n -p 1-65535 --max-rate 100 -oX "$OUT/nmap-full.xml" "$IP"
# IPv6 文档占位符须替换
run_logged nmap-ipv6 nmap -6 -sT -sV -Pn -n -p 80,443 -oX "$OUT/nmap-ipv6.xml" 2001:db8::10
```

XML 解析 host/IP/port/proto/service/product/version；资产键 host+port+proto，TCP/UDP 分开。只有 approved IP 范围里的可用地址进入主动扫描；域名白名单不自动等于 IP 白名单。HTTP/HTTPS 服务再进入 Web 阶段。

| 情况 | 处理 |
|---|---|
| SYN/UDP 权限不足 | 框架 root；人工用 sudo，普通 TCP 可用 -sT |
| 目标无响应 | 区分 filtered/closed/timeout，查原始 XML，不仅看终端 |
| 服务为空 | 保留端口候选，核对 -sV、返回内容和网络设备 |
| 总表看不出 TCP/UDP | 回数据库 proto 或原始 XML 核对 |

依据：本机 nmap -h，[Stage 6](../../asm/stages/s6_port.py)。

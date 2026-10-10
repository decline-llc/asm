# masscan

WSL 1.3.2，Stage 6 的 `ports.engine: masscan` 可调度，完整实际扫描验收待补。原生 JSON 是端口候选，后续 nmap 服务识别不可省略。

```bash
run_logged masscan sudo masscan "$IP" -p80,443 --rate 1000 -oJ "$OUT/masscan.json"
# 网络丢包/限速场景先降低发送速率
run_logged masscan-slow sudo masscan "$IP" -p80,443 --rate 100 -oJ "$OUT/masscan-slow.json"
# 只输出配置，不扫描
run_logged masscan-config masscan "$IP" -p80,443 --rate 100 --echo
# 上述候选开放后，核对具体服务
run_logged masscan-verify nmap -sT -sV -Pn -n -p 80,443 -oX "$OUT/masscan-verify.xml" "$IP"
```

配置 `rates.masscan_rate` 控制主流程速率。不要因 WSL 扫不到就添加任意 adapter/router 参数；先保存接口、网关与网络证据，确定 NAT/raw socket 能力后配置。help/version 在固定版本可能 rc=1，实际扫描非零仍须按 stderr 解释。

输出按 IP+port+proto 去重，再用 nmap 确认；nmap 确认失败保留 review，不把 SYN 候选当存活 Web。

依据：本机 --help/--echo 帮助，[Stage 6](../../asm/stages/s6_port.py)。

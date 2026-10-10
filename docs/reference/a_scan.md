# a_scan.py

位置 `~/asm-ws/tools/a_scan.py`；Python 标准库 TCP connect 备用扫描器。已部署并通过 help，自流程尚未接入。

```bash
run_logged a_scan python3 "$HOME/asm-ws/tools/a_scan.py" --host "$IP" --ports 80,443 --timeout 1 --threads 8
# 较慢网络延长连接超时，降低线程数
run_logged a_scan-slow python3 "$HOME/asm-ws/tools/a_scan.py" --host "$IP" --ports 8000-8010,8443 --timeout 3 --threads 4
run_logged a_scan-help python3 "$HOME/asm-ws/tools/a_scan.py" --help
```

stdout.log 每行一个 JSON：host/port/proto=tcp/service=unknown；可按 JSONL 读取。只输出成功 connect，不识别服务，也不扫描 UDP。检查 rc 后可复制 stdout.log 为 .jsonl；端口候选交 nmap，文件不会自动被 ASM 导入。

| 情况 | 处理 |
|---|---|
| stdout 空 | 可能没有成功连接，核对目标、超时和 stderr |
| 扫描速度低 | 按目标负载调整 threads/timeout，不以空结果断言无服务 |
| 域名给出 fake-IP | 使用批准的可信具体 IP；修复解析路径 |

依据：[a_scan.py](../../tools/scanners/a_scan.py)。

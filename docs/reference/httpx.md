# ProjectDiscovery httpx

固定 1.12.0，WSL `~/asm-ws/bin/httpx`，已安装但尚未接入 Stage 7。当前 Stage 7 用 Windows Python httpx 库。通用 Bash 设置见 [索引](README.md)。

```bash
# 明确 IP allow，保留状态、标题、技术、响应长度
run_logged httpx httpx -l "$OUT/urls.txt" -sc -title -td -cl -j -r "$RESOLVER" -allow "$IP" -t 5 -rl 10 -duc -o "$OUT/httpx.jsonl"
# 选定 Web 端口，输出另存
run_logged httpx-ports httpx -l "$OUT/domains.txt" -p http:80,8080,https:443 -sc -title -j -r "$RESOLVER" -allow "$IP" -rl 10 -duc -o "$OUT/httpx-ports.jsonl"
# 慢服务诊断
run_logged httpx-slow httpx -l "$OUT/urls.txt" -sc -title -j -r "$RESOLVER" -allow "$IP" -t 2 -rl 2 -timeout 20 -duc -o "$OUT/httpx-slow.jsonl"
```

默认不跟随重定向，以上不加 -fr/-fhr。TLS/CSP 中出现的新域名只是候选，不能自动扩大范围；不启用相应扩展探测。JSONL 按 URL 与 host/port/proto 建关系，标题/技术是线索，不证明归属或漏洞。

| 情况 | 处理 |
|---|---|
| allow 后零结果 | 检查真实解析 IP；当前 fake-IP 会被 allow 排除 |
| 403/502 | 保存状态、长度和基线，不判定存在泄露 |
| TLS 失败 | 区分证书、握手超时、代理，核对可信路径 |
| 重定向到外部 | 保存 Location 作 review，框架接入需每跳范围检查 |

依据：本机 httpx -h，当前 [Web 主流程](../../asm/stages/s7_web.py)。

# wafw00f

固定 2.4.2，独立 venv `~/asm-ws/tools/wafw00f/.venv/bin/wafw00f`；已安装，未自动调度。

```bash
run_logged wafw00f wafw00f -r -o "$OUT/wafw00f.json" "$URL"
# 批量输入、明确输出类型、慢网络超时
run_logged wafw00f-batch wafw00f -r -i "$OUT/urls.txt" -f json -T 20 -o "$OUT/wafw00f-batch.json"
# 只列检测指纹
run_logged wafw00f-list wafw00f --list
```

-r 在此工具表示不跟随重定向，与 ffuf -r 含义不同。WAF 指纹帮助解释 403/502 和过滤行为，不证明漏洞、组织归属或 CDN 源站 IP；不同工具的参数不能只按同名字母套用。

| 情况 | 处理 |
|---|---|
| 没检测到 WAF | 可能没有命中已有指纹，不能断言无 WAF |
| 重定向页面无结果 | 保留原状态/Location，再核对目标范围 |
| TLS/连接异常 | 查 stdout/stderr、网络与 DNS，不改变候选置信度 |

依据：本机 wafw00f --help。

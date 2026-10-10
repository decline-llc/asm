# subfinder

固定版本 2.17.0，`~/asm-ws/bin/subfinder`；Stage 4 已自动调用。Bash 变量和 run_logged 见 [索引](README.md)。

```bash
# 当前框架使用的文本输出
run_logged subfinder subfinder -d "$ROOT" -silent -duc -o "$OUT/subdomains.txt"
# 人工核对需要保留提供商标签
run_logged subfinder-sources subfinder -d "$ROOT" -oJ -cs -duc -o "$OUT/subfinder-sources.jsonl"
# 多个批准 root，降低提供商请求速率和等待上限
run_logged subfinder-batch subfinder -dL "$OUT/domains.txt" -oJ -cs -rl 5 -timeout 15 -max-time 5 -duc -o "$OUT/subfinder-batch.jsonl"
# 只列来源，不采集
run_logged subfinder-list subfinder -ls
```

文本每行一个子域；JSONL 保留来源用于比对。按完整标准化域名合并，先做 root/SaaS 范围过滤，再交 DNS；同提供商经多个工具重复取得不算独立归属证据。

额外 key 用 `~/.config/subfinder/provider-config.yaml`，不自动读取 Windows .env。不要把 -all 当默认，未配置 key/限流会影响结果；-recursive 是选择支持递归的来源，不代表主动扫任意子域。

| 情况 | 处理 |
|---|---|
| 返回空 | 看来源/超时/凭据日志，不能直接判“无子域” |
| 某个提供商 429 | 降 -rl，按该提供商额度检查 -rls |
| 只看到假 IP | 此步骤保存的是域名，解析问题交 Stage 5 |

依据：本机 `subfinder -h`（data/validation/reference-help/subfinder.txt），[Stage 4](../../asm/stages/s4_subdomain.py)。

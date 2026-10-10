# nuclei

固定 3.11.1；只确认二进制已安装，模板集未单独验收，主流水线不自动运行漏洞模板。

```bash
# 模板文件须先准备，路径是占位符
TEMPLATE='/path/to/approved-template.yaml'
run_logged nuclei-validate nuclei -t "$TEMPLATE" -validate -duc
run_logged nuclei nuclei -u "$URL" -t "$TEMPLATE" -dr -ni -duc -rl 10 -jsonl -o "$OUT/nuclei.jsonl"
# 批量批准 URL，降低并发
run_logged nuclei-batch nuclei -l "$OUT/urls.txt" -t "$TEMPLATE" -dr -ni -duc -rl 5 -c 2 -jsonl -o "$OUT/nuclei-batch.jsonl"
run_logged nuclei-help nuclei -h
```

-dr 关闭 HTTP 模板跳转，-ni 排除 OAST；具体请求行为仍取决于模板。选择模板并阅读实际请求、匹配条件后运行；不把默认全模板集当成已完成暴露面核验。

JSONL 按模板、目标和证据复查；匹配可能来自统一返回页、过滤页或版本猜测。只归档必要的响应/证据并检查敏感字段，人工确认后再决定状态，不自动当作确认漏洞。

| 情况 | 处理 |
|---|---|
| 模板不存在 | 核对显式 -t；安装二进制不保证模板文件存在 |
| validate 失败 | 看语法/签名/依赖，按固定版本修复 |
| 命中很多相同结果 | 对照不存在路径、状态和原始匹配条件 |
| 结果为空 | 检查模板加载数量、适用协议、错误/超时，不断言无问题 |

依据：本机 nuclei -h。

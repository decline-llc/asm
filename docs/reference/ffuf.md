# ffuf

固定 2.3.0，已安装、未接入 Stage 7。输入字典是候选集合，不是资产事实。

```bash
# 初步保留所有状态，避免 403/502 被默认匹配规则忽略
run_logged ffuf ffuf -u "$URL/FUZZ" -w "$WORDLIST" -mc all -rate 50 -t 5 -noninteractive -of json -o "$OUT/ffuf.json"
# 有统一返回页时另跑自动校准，原始结果仍保留
run_logged ffuf-calibrated ffuf -u "$URL/FUZZ" -w "$WORDLIST" -ac -mc all -rate 10 -t 2 -noninteractive -of json -o "$OUT/ffuf-calibrated.json"
# 明确测得统一返回长度后再过滤；1234 仅是占位测量值
run_logged ffuf-size ffuf -u "$URL/FUZZ" -w "$WORDLIST" -mc all -fs 1234 -rate 10 -noninteractive -of json -o "$OUT/ffuf-size.json"
# 原生多格式结果留作人工阅读
run_logged ffuf-formats ffuf -u "$URL/FUZZ" -w "$WORDLIST" -rate 10 -noninteractive -of all -o "$OUT/ffuf-formats"
```

默认不跟随跳转，以上不加 -r。JSON 中 status/length/words/lines/URL 结合三个不存在路径的基线核对；-ac 不能代替原始记录和人工判断。过滤条件过宽会漏真实页面，502 单独只作为候选。

| 情况 | 处理 |
|---|---|
| 几乎每条都命中 | 看统一返回页，保存未过滤与校准两份结果 |
| 超时/服务负载增加 | 降 -rate/-t，调整 -timeout，检查 stderr |
| 字典不存在 | SecLists 当前稀疏检出，先核对实际文件 |
| JSON 结果没进总表 | 原生 ffuf 尚无自动导入适配器 |

依据：本机 ffuf -h（data/validation/reference-help/ffuf.txt）。

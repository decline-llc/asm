# katana

固定 1.8.0，已安装、未接入 Stage 7。默认 rdn 范围和跟随跳转不能直接当作精确项目边界。

```bash
# scope 的占位主机需与 URL 一起改为批准主机
SCOPE='^https://authorized\.invalid(?::443)?(?:/|$)'
run_logged katana katana -u "$URL" -cs "$SCOPE" -dr -duc -d 2 -rl 10 -j -or -ob -o "$OUT/katana.jsonl"
# JS 端点线索，仍保持同一精确范围
run_logged katana-js katana -u "$URL" -cs "$SCOPE" -dr -duc -jc -d 3 -rl 5 -j -or -ob -o "$OUT/katana-js.jsonl"
# robots/sitemap 已知文件，深度至少 3
run_logged katana-known katana -u "$URL" -cs "$SCOPE" -dr -duc -kf all -d 3 -rl 5 -j -or -ob -o "$OUT/katana-known.jsonl"
```

URL/JS/表单结果先做范围过滤，再按完整 URL 保留；查询参数排序等语义去重需另行处理。-or/-ob 减少原始请求/响应正文存储，需要正文证据时另行选择并脱敏。JS 中出现链接不表示已经存在服务。

| 情况 | 处理 |
|---|---|
| 跳转后没继续 | -dr 是显式关闭；人工核对 Location 范围 |
| 范围看起来太大 | 检查 -cs 正则主机边界和默认 -fs rdn |
| 动态页面少结果 | 普通爬取不等于浏览器执行；headless 接入需请求范围控制 |
| 发现凭据样文本 | 不启用向提供商发送验证请求的 secret validation |

依据：本机 katana -h；未来自动接入须用回环夹具证明越界请求零到达。

# gowitness

固定 3.2.0，WSL 已安装；每个浏览器请求的范围控制尚待实现，当前主流程由 Windows Playwright 截图。以下先用于运行中的 WSL 回环 fixture。

```bash
printf '%s\n' 'http://127.0.0.1:8765' > "$OUT/local-urls.txt"
run_logged gowitness gowitness scan file -f "$OUT/local-urls.txt" --chrome-path /usr/bin/google-chrome --write-jsonl --write-jsonl-file "$OUT/gowitness.jsonl" --screenshot-format png --screenshot-path "$OUT/screenshots"
# 页面尺寸与慢页面等待
run_logged gowitness-slow gowitness scan file -f "$OUT/local-urls.txt" --chrome-path /usr/bin/google-chrome --chrome-window-x 1280 --chrome-window-y 720 -T 90 --log-scan-errors --write-jsonl --write-jsonl-file "$OUT/gowitness-slow.jsonl" --screenshot-format png --screenshot-path "$OUT/screenshots-slow"
run_logged gowitness-help gowitness scan file --help
```

默认图片为 JPEG，元数据需显式 writer flag。保存 JSONL 和图片的关联，核对失败项、最终 URL、状态和页面标题；输入 URL 被限制还不能保证页面外部子资源/导航不越界。

| 情况 | 处理 |
|---|---|
| 自动下载浏览器 | 明确 --chrome-path 指向已安装 Chrome |
| 有图没元数据 | 检查 --write-jsonl 和指定文件 |
| 图片格式不合报告 | 指定 png；ASM 当前读取 PNG |
| Windows fixture 访问不到 | NAT 两侧回环不同，启动 WSL 侧夹具 |
| 图片搬走后链接失效 | 元数据/图片一起留存；ASM HTML 导出会内嵌已入库截图 |

依据：本机 gowitness scan file --help。

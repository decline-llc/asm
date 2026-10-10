# gowitness（Web 截图）

> 状态：**仅安装，尚待“每个浏览器请求”的范围控制**；当前主流程截图由 Windows Playwright 承担（见 [playwright.md](playwright.md)）
> 版本：3.2.0（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/gowitness`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/gowitness.txt`、`web-tool-help/gowitness.txt`）
> 证据：本机 `gowitness scan file --help`

## 1. 用途、场景与局限

- **用途**：对 URL 列表批量做浏览器截图并保存元数据（最终 URL、状态、标题、TLS 等）。
- **适用场景**：目前在**运行中的 WSL 回环 fixture** 上核对参数与输出；未来作为 WSL 侧截图引擎。
- **局限**：**仅限制输入 URL 还不够**——页面加载的外部子资源、导航、重定向可能越界；接入生产前必须实现“每个浏览器请求”的范围控制。**默认图片是 JPEG**，**默认不一定保存元数据**（需显式 writer flag）。当前 ASM 报告读取 PNG。
- **接入状态**：已安装、未接入；不自动入库。Windows Playwright 是当前唯一接入的截图链。

## 2. 实际接入状态

无自动调度。生产接入前需解决：浏览器导航、子资源与每个请求的范围约束（不能只靠输入 URL 过滤）。`--chrome-path` 必须显式指向已安装 Chrome，避免自动下载不受控的浏览器。

## 3. 输入准备与场景命令（WSL 回环 fixture 先行验证）

> 前置：WSL、fixture 在 WSL 侧回环监听（示例 `127.0.0.1:8765`，按需启动）；`--chrome-path` 指向已装 Chrome。通用变量/`run_logged` 见 [索引](README.md)。

```bash
printf '%s\n' 'http://127.0.0.1:8765' > "$OUT/local-urls.txt"
# 指定 Chrome、显式写 JSONL 元数据、PNG 格式
run_logged gowitness gowitness scan file -f "$OUT/local-urls.txt" \
  --chrome-path /usr/bin/google-chrome --write-jsonl --write-jsonl-file "$OUT/gowitness.jsonl" \
  --screenshot-format png --screenshot-path "$OUT/screenshots"
# 页面尺寸与慢页面等待
run_logged gowitness-slow gowitness scan file -f "$OUT/local-urls.txt" \
  --chrome-path /usr/bin/google-chrome --chrome-window-x 1280 --chrome-window-y 720 -T 90 \
  --log-scan-errors --write-jsonl --write-jsonl-file "$OUT/gowitness-slow.jsonl" \
  --screenshot-format png --screenshot-path "$OUT/screenshots-slow"
run_logged gowitness-help gowitness scan file --help
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 基础截图 | WSL | 回环 fixture+Chrome | `-f` 文件、`--chrome-path`、`--write-jsonl(-file)`、`--screenshot-format png`、`--screenshot-path` | `$OUT/gowitness.jsonl`+PNG | 每 URL 一条+图片 | rc≠0；无图且无元数据 |
| 慢页面 | WSL | 同上 | `--chrome-window-x/y`、`-T` 超时、`--log-scan-errors` | `$OUT/gowitness-slow.jsonl`+PNG | 慢页留证 | stderr 超时记录 |
| `--help` | 任意 | — | — | stdout 文本 | 打印帮助 | — |

**参数含义**（本机 3.2.0）：`-t` 线程（默认 6）、`-T` 页面超时秒（默认 60）、`--delay` 导航到截图的等待秒（默认 3）、`--screenshot-format`（默认 `jpeg`，ASM 需 `png`）、`--write-jsonl(-file)`、`--write-db(-uri)`、`--chrome-proxy`、`--log-scan-errors`。`--write-*` 系列需显式开才有元数据。

## 4. 原生输出格式与解析

- **JSONL**（`--write-jsonl-file`）：逐行对象，含 `url`、`final_url`、`response_code`、`title`、`screenshot_file`、`tls`、失败记录等。脱敏样例：

  ```json
  {"url":"http://127.0.0.1:8765","final_url":"http://127.0.0.1:8765/","response_code":200,"title":"Fixture Portal","screenshot_file":"screenshots/http---127.0.0.1-8765.png"}
  ```

- **PNG/JPEG**：按 `--screenshot-path` 目录；文件名由 URL 派生。
- **解析方法**：逐行 `json.loads`；用 `screenshot_file` 关联图片；核对 `response_code`/`title` 与失败项（`--log-scan-errors` 的 stderr）。

## 5. 结果衔接与入库

- 衔接：截图+元数据 → 报告证据；与 httpx/Stage 7 结果对照。
- 入库：**当前不自动入库**；ASM 报告内嵌的是 Playwright 已采集的 PNG，不读取 gowitness 目录。

## 6. 去重、来源与复核

- 去重键：输入 URL；同名文件覆盖需用独立输出目录区分运行。
- 来源保留：JSONL 与图片同目录留存，保持关联。
- 时间戳：保存 `started-utc.txt` 与 rc；JSONL 记录观测时间。
- 独立复核：图片存在性、尺寸、与 `final_url`/`response_code` 一致性。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 自动下载浏览器 | 明确 `--chrome-path` 指向已安装 Chrome |
| 有图没元数据 | 检查 `--write-jsonl` 与指定文件路径 |
| 图片格式不合报告 | 指定 `--screenshot-format png`（ASM 读 PNG；默认 jpeg） |
| Windows fixture 访问不到 | NAT 两侧回环不同；启动 WSL 侧夹具 |
| 图片搬走后链接失效 | 元数据/图片一起留存；ASM HTML 内嵌已入库截图 |
| 越界子资源 | 这是当前未接入的关键原因；接入前须证明请求级范围控制 |

## 8. 官方来源与核对记录

- 官方仓库核对：[sensepost/gowitness](https://github.com/sensepost/gowitness)；版本 3.2.0 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`gowitness scan file --help` 原文 `data/validation/reference-help/gowitness.txt` 与 `data/validation/web-tool-help/gowitness.txt`。
- 待验证：每个浏览器请求（导航/子资源/重定向）的范围控制实现；与 Playwright 截图的一致性；真实目标稳定性。

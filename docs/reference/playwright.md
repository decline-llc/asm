# Windows Playwright / Chromium（截图）

> 状态：**已自动调用**（Stage 7 首页截图）
> 版本：Playwright 1.63.0（Python 库）；Chromium 浏览器已由 `playwright install chromium` 安装
> 核对日期：2026-10-10（回环实测：截图与离线 HTML 集成测试通过，见 ACCEPTANCE）
> 证据：本机源码 [s7_web.py](../../asm/stages/s7_web.py)、集成测试 [test_local_web.py](../../tests/integration/test_local_web.py)

## 1. 用途、场景与局限

- **用途**：在主动 Web 阶段对每个 Web 资产首页做真实浏览器截图，生成 PNG 作为页面证据；同时截图过程承担“每个浏览器请求都做范围控制”的防线。
- **适用场景**：Stage 7 对 `web.urls` 与端口服务派生的 HTTP(S) URL 截取首页；Stage 8 把 PNG 按总表序号复制并在 HTML 内嵌展示。
- **局限**：只截首页（`wait_until="domcontentloaded"`、full_page），不做登录、不做交互、不做整站爬取；被动模式（`--passive-only`）不运行 Stage 7，因此**被动报告没有截图**；普通 TCP/UDP 非 Web 服务也没有截图。HTML 报告内嵌的是“已采集”的 PNG，**不能恢复当时未采集或已丢失的截图**。
- **安装位置**：Windows `.venv` 内 `playwright` 包 + 其下载的 Chromium；不是 WSL 的 Google Chrome（两者是不同运行时，见 [chrome.md](chrome.md)）。

## 2. 实际接入状态

由 `s7_web.py` 的 `screenshot()` 在 Stage 7 中调用，非独立 CLI 工具。每个请求经 `context.route("**/*", route)` 回调：非 http/https scheme 直接 `abort()`，`ctx.scope.assert_in_scope(hostname)` 越界则阻断并记录 `screenshot_scope_block` review。浏览器上下文禁用 service worker、不接受下载。PNG 保存为 `data/<profile>/screenshots/asset-<asset_id>.png`，并把路径写回 `urls.screenshot`。

## 3. 场景命令（PowerShell 7，仓库根目录）

> 前置：已 `pip install -e .[dev,browser]`；首次或浏览器缺失时先 `python -m playwright install chromium`。截图属于主动阶段，需要 profile `authorization: true` 且非 `--passive-only`。

```powershell
# 查看库版本
.\.venv\Scripts\python.exe -m playwright --version
# 新机器或浏览器缺失时安装
.\.venv\Scripts\python.exe -m playwright install chromium
# 主动 Web 阶段（customer 须先完成范围/授权配置）
.\.venv\Scripts\python.exe -m asm stage 7 --profile customer
# 本地完整回环链路（含截图与三格式报告）
.\.venv\Scripts\python.exe scripts/local-demo.py
# 定向验证：截图、搬走 HTML、离线/禁用 JS 的浏览器行为
.\.venv\Scripts\python.exe -m pytest tests/integration/test_local_web.py -k screenshot -q
```

| 命令 | 运行环境 | 前置条件 | 关键参数 | 输出位置 | 预期结果 | 失败判定 |
|---|---|---|---|---|---|---|
| `playwright install chromium` | Windows | 已装 .venv | — | Playwright 浏览器缓存目录 | Chromium 就绪 | 下载失败/网络错误 |
| `asm stage 7` | Windows | 授权+非被动+已有资产/URL | profile `web.urls`、`web.screenshots` | `data/<profile>/screenshots/asset-<id>.png`、`urls.screenshot` | Web 资产产生 PNG | 阶段 failed/partial；无 URL 时 count=0 |
| `pytest -k screenshot` | Windows | 测试依赖 | `-k` 过滤 | 测试断言 | 通过 | 断言失败/CSP 或截图断言不成立 |

**参数含义**（代码内固定，非 CLI 暴露）：`wait_until="domcontentloaded"`、`timeout=15000ms`、`full_page=True`、`service_workers="block"`、`accept_downloads=False`。窗口/视口使用 Playwright 默认值。`web.screenshots: false` 可整体关闭截图（配置项）。

## 4. 输出格式与解析

- 原生输出是 **PNG 文件**（`asset-<id>.png`），路径回写 `urls.screenshot`（文本）。Stage 8 再按总表序号复制为 `screenshots/<序号>.png` 并在 HTML 以 data URI 内嵌。
- 复核时对照数据库：`SELECT url, screenshot FROM urls;`，确认 PNG 文件存在且为有效图片。样例 `data/test/screenshots/1.png` 为 1280×720 的 Fixture Portal（回环数据，非公网资产）。

## 5. 结果衔接与入库

- 输入：Stage 6 的 TCP Web 服务（`service in {http,https,ssl/http,http-proxy}` 或端口 80/443/8765）派生的 URL，加上 profile `web.urls`。
- 输出：`urls.screenshot` 字段入库；Stage 8 报告引用。
- 截图本身入库的是路径（文本），PNG 文件留在 `data/<profile>/screenshots/`；HTML 导出时才内嵌。

## 6. 去重、来源与复核

- URL 以完整字符串为键（见索引）；同一 URL 重复 Stage 7 会覆盖 `screenshot` 路径为最新一次采集。
- 时间戳以流水线运行日志为准；PNG 文件本身的 mtime 可作旁证。
- 独立复核：对每资产检查 `asset-<id>.png` 与 `screenshots/<序号>.png` 是否存在、尺寸是否符合视口；阻断记录见 `findings` 中 `screenshot_scope_block`。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 被动模式没图 | 模式差异：Stage 7 未运行，不是故障 |
| 有图但 Excel 点不开 | 相对路径需要 `screenshots/` 同目录；或打开自包含 HTML |
| 原始图片缺失 | 核对 `urls.screenshot` 与 Stage 7 日志；HTML 无法重新生成缺失截图 |
| Chromium 未安装 | doctor/定向测试会明确指出；按 `playwright install chromium` 修复 |
| 截图白屏/超时 | 目标慢或需 JS 渲染超时；核对 Stage 7 notes、目标可达性与 TLS/代理 |
| 范围外子资源被拦 | 查看 `screenshot_scope_block`；这是预期防线，不要关闭 scope 检查来“修复” |
| 截图与页面不一致 | 以浏览器实采 PNG 为准；PNG 不能替代归属核对或漏洞确认 |

## 8. 官方来源与核对记录

- 官方文档核对：Playwright Python 文档（[playwright.dev/python](https://playwright.dev/python/)）——`route`/`abort`、`new_context` 参数与官方一致；版本以本机 `pip show playwright` 1.63.0 为准。
- 本机证据：源码 [s7_web.py](../../asm/stages/s7_web.py)；集成测试 [test_local_web.py](../../tests/integration/test_local_web.py)；样例截图 `data/test/screenshots/1.png`；HTML 离线核验 `data/validation/report-formats-preview/checks.json`。
- 待验证：真实公网目标在可信解析路径建立后的截图稳定性与视觉核验。

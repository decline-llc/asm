# 验证

`python -m pytest -q` 默认验证离线解析、本地 HTTP、报表、范围规则和配额。

真实 WSL 验证：PowerShell 7 设置 `$env:ASM_TEST_WSL='1'` 后运行 pytest。WSL fixture 只在 Linux 回环监听，因为 WSL NAT 下 Linux localhost 与 Windows localhost 不同。`slow` 测试实际等 15 秒验证 FOFA 硬下限，无外部 API 请求。

fixtures 只用 example.invalid、文档 IP 和 PERSON/PHONE 占位符。不得添加真实客户数据库或凭据。browser 测试需 Playwright Chromium；未安装时会显式 skip。

2026-10-10 Session 006 完整验收 **60 passed in 69.22s、0 failures/errors/skipped**，包括 9 项真实 WSL 验证，JUnit 为 data/validation/report-formats-full.xml。`fixtures/dns_server.py` 用 stdlib 在 Windows/WSL 回环提供 UDP/TCP DNS；原生 WSL 测试自动分配三组端口，验证 dnsx/dig 五类记录、优先地址修正、CNAME 链及异常。Windows dnspython 复核使用单独 Windows 服务，避免 NAT 回环混淆。悬空链不会单独产生 takeover；HTTP 指纹分支用模拟响应验证。公网目标和 API 账户未纳入这组测试。

`unit/test_report_formats.py` 验证八表 CSV/XLSX 字段与数值、中文 BOM、逗号/引号/换行、公式前缀转义、D 级隔离、HTML 转义与 CSP、缺失/不可读/非 PNG 截图、空表、三种输出后缀及默认 Stage 8 的分支结果。`integration/test_local_web.py` 使用实际 Playwright PNG，将唯一 HTML 文件移动到新目录后以离线浏览器验证图片、搜索、零外部 HTTP 请求，并验证禁用 JavaScript 时仍可查看表格与图片。浏览器测试使用 Playwright expect 等待图片加载，不依赖 CSP 禁止的字符串 eval。

OneForAll 测试通过生产调度器写入隔离任务，调用实际固定版本 venv 内的 Collect、七个被动模块、SQLite 与导出。夹具仅替换 HTTP transport，所有 socket 网络请求阻断；验证七来源合并、AlienVault 双端点、不同 root 隔离、成功缓存、空结果、部分失败、模块/任务超时和失败重试。可用 `pytest tests/unit/test_oneforall.py tests/integration/test_wsl.py -k oneforall` 定向重跑；ASM_TEST_WSL 未开启时原生部分明确 skip，CI 用 `-m 'not wsl'`。

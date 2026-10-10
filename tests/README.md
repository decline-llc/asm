# 验证

`python -m pytest -q` 默认验证离线解析、本地 HTTP、报表、范围规则和配额。

真实 WSL 验证：PowerShell 7 设置 `$env:ASM_TEST_WSL='1'` 后运行 pytest。WSL fixture 只在 Linux 回环监听，因为 WSL NAT 下 Linux localhost 与 Windows localhost 不同。`slow` 测试实际等 15 秒验证 FOFA 硬下限，无外部 API 请求。

fixtures 只用 example.invalid、文档 IP 和 PERSON/PHONE 占位符。不得添加真实客户数据库或凭据。browser 测试需 Playwright Chromium；未安装时会显式 skip。

2026-10-10 完整验收 35 passed、0 skipped。`fixtures/dns_server.py` 用 stdlib 在 Windows/WSL 回环提供 UDP/TCP DNS；原生 WSL 测试自动分配三组端口，验证 dnsx/dig 五类记录、优先地址修正、CNAME 链及异常。Windows dnspython 复核使用单独 Windows 服务，避免 NAT 回环混淆。悬空链不会单独产生 takeover；HTTP 指纹分支用模拟响应验证。公网目标和 API 账户未纳入这组测试。

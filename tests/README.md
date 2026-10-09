# 验证

`python -m pytest -q` 默认验证离线解析、本地 HTTP、报表、范围规则和配额。

真实 WSL 验证：PowerShell 7 设置 `$env:ASM_TEST_WSL='1'` 后运行 pytest。WSL fixture 只在 Linux 回环监听，因为 WSL NAT 下 Linux localhost 与 Windows localhost 不同。`slow` 测试实际等 15 秒验证 FOFA 硬下限，无外部 API 请求。

fixtures 只用 example.invalid、文档 IP 和 PERSON/PHONE 占位符。不得添加真实客户数据库或凭据。browser 测试需 Playwright Chromium；未安装时会显式 skip。

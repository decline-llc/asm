# Windows Playwright

Playwright 1.63.0，Chromium 已安装；当前 Stage 7 自动截图。以下在 PowerShell 7 执行。

```powershell
.\.venv\Scripts\python.exe -m playwright --version
# 新机器或浏览器缺失时安装
.\.venv\Scripts\python.exe -m playwright install chromium
# 项目主动 Web 阶段，customer 须完成范围配置
.\.venv\Scripts\python.exe -m asm stage 7 --profile customer
# 本地完整链路
.\.venv\Scripts\python.exe scripts/local-demo.py
# 截图、移走 HTML、离线/禁用 JS 的浏览器验收
.\.venv\Scripts\python.exe -m pytest tests/integration/test_local_web.py -k screenshot -q
```

Stage 7 按每个浏览器请求限制 scope，阻断越界导航/子资源，禁用 service worker/下载；PNG 保存 asset-id，Stage 8 按总表序号复制。HTML 内嵌这些已采集 PNG，不靠浏览器重新请求目标。

| 情况 | 处理 |
|---|---|
| passive-only 没图 | 主动 Web 阶段未运行，属于模式差异 |
| 有图但 Excel 点不开 | 保留 screenshots/，或打开自包含 HTML |
| 原始图片缺失 | 核对数据库 urls.screenshot 和 Stage 7 日志；HTML无法重新生成缺失截图 |
| Chromium 未安装 | doctor/定向测试会明确指出，按安装入口修复 |

依据：[s7_web.py](../../asm/stages/s7_web.py)、[离线报告浏览器测试](../../tests/integration/test_local_web.py)。

# ASM 命令与报告

位置：Windows `D:\Desktop\asm\.venv`；Python 3.11.9。以下命令在 PowerShell 7 执行。

```powershell
# 入口和部署检查
.\.venv\Scripts\python.exe -m asm --help
.\.venv\Scripts\python.exe -m asm doctor --json-output
# 新机器部署；本机已安装，无需每次重复
.\.venv\Scripts\python.exe -m asm init-wsl --distro Ubuntu
# 完全离线的 fixture 演示
.\.venv\Scripts\python.exe -m asm run --profile demo --dry-run --passive-only
# 本地真实端口、Web、截图、三格式报告
.\.venv\Scripts\python.exe scripts/local-demo.py
# customer 须先创建，基础被动域名/DNS链路
.\.venv\Scripts\python.exe -m asm run --profile customer --stages 1,3,4,5,8 --passive-only
# 恢复完成配置的主动项目
.\.venv\Scripts\python.exe -m asm run --profile customer --stages 1,2a,2b,3,4,5,6,7,p1,p2,8 --resume
# 仅重导出，不重采集
.\.venv\Scripts\python.exe -m asm report --profile test
# 指定同一套导出的文件名前缀，三个后缀均可
.\.venv\Scripts\python.exe -m asm report --profile test --output data/test/delivery.html
# 配额查询不发送 API 请求
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

默认导出 `report.xlsx`、总表 `report.csv`、七明细 `report-csv/*.csv`、独立 `report.html`。HTML 把可读取 PNG 内嵌，单独搬走可以离线查看；CSV 用 UTF-8 BOM，公式起始字符以文本转义。xlsx/CSV 的截图路径仍相对于 screenshots/，一起交付。

默认阶段 8 已放在 p1/p2 后；显式 --stages 由调用者安排。--resume 跳过同配置已完成阶段；工具成功缓存是另一层，需要全新采集用新项目库。failed/partial 返回非零但有效结果仍保留。

| 场景 | 核对 |
|---|---|
| 没有数据库 | 先 run 种子/采集，report 不自动扫描 |
| 主动阶段被拒绝 | 检查 authorization、passive-only、域名/IP 两类范围 |
| 报告缺支路结果 | 看显式阶段顺序，或采集后 report 重新导出 |
| xlsx 截图链接失效 | 保留 screenshots/；独立 HTML 已内嵌图片 |
| HTML 无截图 | 区分未采集、文件缺失、读取/PNG 异常；报告不能重建未保存图片 |

依据：[cli.py](../../asm/cli.py)、[s8_report.py](../../asm/stages/s8_report.py)、[report_html.py](../../asm/report_html.py)。

# 脱敏测试输入

`equity.json` 覆盖 51% 控股、孙公司与非控股剔除；`icp.json` 覆盖 footer、无号、跳转、WAF、失联；`dns.json` 包含普通与 CDN 记录；`sourcegraph.sse` 和 `tender.txt` 验证 OSINT 解析。

`server.py` 模拟登录、Actuator、API、文件泄露、robots/sitemap、403/502 和 catch-all。内容为显式虚构占位，没有实际泄露材料。

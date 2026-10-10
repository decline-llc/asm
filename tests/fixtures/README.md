# 脱敏测试输入

`equity.json` 覆盖 51% 控股、孙公司与非控股剔除；`icp.json` 覆盖 footer、无号、跳转、WAF、失联；`dns.json` 包含普通与 CDN 记录；`sourcegraph.sse` 和 `tender.txt` 验证 OSINT 解析。

`server.py` 模拟登录、Actuator、API、文件泄露、robots/sitemap、403/502 和 catch-all。内容为显式虚构占位，没有实际泄露材料。

`dns_server.py` 提供回环 UDP/TCP DNS 响应与超时分支。`oneforall_probe.py` 仅在集成测试中注入：运行真实固定版本采集/数据库/导出，替换 HTTP transport 为虚构响应，阻断全部 socket 连接并记录请求。提供双端点独有子域、空响应、503、模块及整任务超时，不包含外部凭据，不参与生产流水线。

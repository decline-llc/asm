# v2.0 覆盖与继续实施清单

本版是可运行基础实现。功能入口存在不代表完整方法论验收。

| 模块 | 已实现 | 尚需补齐/实测 |
|---|---|---|
| 数据治理 | 契约表、即时提交、来源合并、隔离、无效观测、facts、配置指纹恢复 | 更细置信度升级人工审计与数据库迁移 |
| WSL 桥 | 原生路径校验、字节管道、tar 防目录穿越、root、Linux timeout、异步 Popen、60s 转后台、失败 marker | 挂起探活/单次被动重试、孤儿 PID 丢失诊断、24h 性能基线 |
| seed | 公司/品牌/域名/IP 标准化与记录 | RDAP、逆向 DNS enrich |
| equity | 六阶段 fixture 回放、51% 递归、SPV null、人工导入、同页预热接口 | 第三方网站真实 selectors、人工值守实网、公众号与完整 WebSearch 兜底 |
| ICP | 5 种分支、已观测子号解析、人工导入、授权 footer | 搜索快照/工信部自动兜底、主体反查；被动模式绝不直接请求目标 footer |
| subdomain | subfinder、crt.sh、HackerTarget、CDX、FOFA/Quake、有授权 DNS 字典与通配符 | OneForAll 调度、VT/DNSDumpster/Amass、搜索与拼音、JS 回流、引擎优先级路由 |
| DNS/CDN | A/AAAA/MX/NS/CNAME、CDN 指纹、分流与修正函数、接管证据函数 | dnsx/dig 三解析商真实组合、链终点接管/NS/MX 现场证据、历史 IP/归源路径 |
| ports | root nmap TCP/UDP、masscan 选项、结果入库、蜜罐、/24 聚类 | 主链 Top1000→全端口二段、Quake/FOFA IP enrich、TLS SAN 回流、宝塔/favicon/完整差分指纹 |
| web | scope 每跳、bounded response、全部内置路由+泄露、catch-all、robots/sitemap、Java 路径、CORS 候选、Playwright 截图 | WSL httpx/gowitness/ffuf/katana 接入、JS 端点、版本矩阵、CDN 现场差分、可选参数工具 |
| report | 严格总表+7 sheet、可信 SQL、截图按总表行号、相对链接、防公式注入、八表逐页视觉核验 | 更多资产业务标签与真实数据版式回归 |
| panel | 六引擎 fixture 解析、FOFA dot syntax/≥15s/≤200、持久账本、分页、Quake 子域切分 | 真实各家账户校验、Censys 旧 API 迁移评估、跨 profile 的共享额度、IP段细分 |
| OSINT | 特定词拒绝泛词、SSE 流、公告四合一、导入反哺 | 更多来源、人员图谱、实际服务限流与 API 可用性 |
| supply | cert A 路、B 路人工证据卡、六维清单、证书8次额度 | 高价值6 IP全端口专用限额、供应商案例实网、两路并发 |

不得把 502 单独当作泄露或端点存在的证明。本实现将其记录为 `backend_filtered_candidate`，需人工结合基线、其它状态和归属确认。

未获得用户指定的自有测试域名和 API credentials 前，不运行外部主动测试。`test.yaml` 只授权回环 fixture。

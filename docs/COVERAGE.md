# v2.0 覆盖与继续实施清单

本版是可运行基础实现。功能入口存在不代表完整方法论验收。

| 模块 | 已实现 | 尚需补齐/实测 |
|---|---|---|
| 数据治理 | 契约表、即时提交、来源合并、隔离、无效观测、facts、配置指纹恢复 | 更细置信度升级人工审计与数据库迁移 |
| WSL 桥 | 原生路径校验、字节管道、tar 防目录穿越、root、Linux timeout、异步 Popen、60s 转后台、失败 marker | 挂起探活/单次被动重试、孤儿 PID 丢失诊断、24h 性能基线 |
| seed | 公司/品牌/域名/IP 标准化与记录 | RDAP、逆向 DNS enrich |
| equity | 六阶段 fixture 回放、51% 递归、SPV null、人工导入、同页预热接口 | 第三方网站真实 selectors、人工值守实网、公众号与完整 WebSearch 兜底 |
| ICP | 5 种分支、已观测子号解析、人工导入、授权 footer | 搜索快照/工信部自动兜底、主体反查；被动模式绝不直接请求目标 footer |
| subdomain | subfinder、OneForAll 七来源白名单被动调度（默认五个）、crt.sh、HackerTarget、CDX、FOFA/Quake、有授权 DNS 字典与通配符；来源合并、独立任务目录、失败/超时证据和成功复用；字典使用显式优先上游并过滤不可用地址 | OneForAll 公网接口/已知子域覆盖率、VT/DNSDumpster/Amass、搜索与拼音、JS 回流、引擎优先级路由 |
| DNS/CDN | WSL dnsx/dig 三上游 A/AAAA/MX/NS/CNAME、Windows 显式复核、各来源及差异证据、优先上游修正、0.0.0.0/::/fake-IP 隔离、链终点/环路/上限/悬空、CDN 分流、可选原始域名 HTTP 接管指纹 review；端口/域名报告使用修正地址 | 优先修复两端显式公共 UDP/TCP 53 仍被 fake-IP 影响的解析路径；DoH 适配器/可信转发器、自有域名现场证据、真实接管 HTTP 指纹、NS/MX 可注册性核验、历史 IP/归源路径 |
| ports | root nmap TCP/UDP、masscan 选项、结果入库、蜜罐、/24 聚类 | 主链 Top1000→全端口二段、Quake/FOFA IP enrich、TLS SAN 回流、宝塔/favicon/完整差分指纹 |
| web | scope 每跳、bounded response、全部内置路由+泄露、catch-all、robots/sitemap、Java 路径、CORS 候选、Playwright 截图 | WSL httpx/gowitness/ffuf/katana 接入、JS 端点、版本矩阵、CDN 现场差分、可选参数工具 |
| report | 严格总表+7 sheet、可信 SQL、截图按总表行号、相对链接、防公式注入、八表逐页视觉核验 | HTML 结果报告尚未实现；更多资产业务标签与真实数据版式回归 |
| panel | 六引擎 fixture 解析、FOFA dot syntax/≥15s/≤200、持久账本、分页、Quake 子域切分 | 真实各家账户校验、Censys 旧 API 迁移评估、跨 profile 的共享额度、IP段细分 |
| OSINT | 特定词拒绝泛词、SSE 流、公告四合一、导入反哺 | 更多来源、人员图谱、实际服务限流与 API 可用性 |
| supply | cert A 路、B 路人工证据卡、六维清单、证书8次额度 | 高价值6 IP全端口专用限额、供应商案例实网、两路并发 |

不得把 502 单独当作泄露或端点存在的证明。本实现将其记录为 `backend_filtered_candidate`，需人工结合基线、其它状态和归属确认。

DNS 组合已用三组原生 WSL 回环 DNS 服务实测；Windows dnspython 用 Windows 回环服务独立实测。接管 HTTP 分支仅做模拟响应验证，未进行公网资源注册或真实接管验证。IPv6 DNS 地址选择与报告已验证，nmap 按地址族设置 -6；IPv6 主动端口链路仍待原生实测。

Session 005 公网抽检：Windows/WSL 的系统及三个显式上游 UDP/TCP 53 对 example.com 都返回 198.18.0.122；HTTPS DNS 对照取得公网地址。六个公开 HTTPS 主页均有响应，但未验证认证 API 或完整 OneForAll 来源。修复可信 DNS 路径优先于实网资产核对；详细安装/接入差别、输出和报告样例见 OPERATIONS.md。

OneForAll 在真实 WSL venv 中执行固定版本 Collect、Module、SQLite 和 JSON 导出，HTTP 传输替换为离线响应，所有网络连接均由测试夹具阻断。已验证七来源、两个 AlienVault 端点合并、空结果、部分失败、模块/任务超时、不同 root 隔离和成功复用；这些证据不代表公网提供商可达性或覆盖率。没有调用上游默认 run/main，避免其隐含 wildcard/SRV 查询和注册域扩张。

未获得用户指定的自有测试域名和 API credentials 前，不运行外部主动测试。`test.yaml` 只授权回环 fixture。

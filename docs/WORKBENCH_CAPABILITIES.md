# ASM Workbench 实施与验收覆盖

更新：2026-10-11，Asia/Shanghai。完整产品验收尚未完成。本文记录代码与证据，不将模式支持、工具安装、Mock 或配置可加载等同于实际实跑。

2026-10-12补充：已有工具的完整流程适配器已扩展，见 [TOOL_INTEGRATION](TOOL_INTEGRATION.md)。新增naabu/a_scan、dnsx/dig、OneForAll统一live job、httpx/ffuf/katana/gowitness/nuclei/wafw00f及SecLists输入接入；本批全单元回归317通过，最终相关回归90通过。原WSL `Ubuntu` 已在正式主机权限下核实，早先空列表判断错误；原工具安装保留。dig/dnsx、naabu/a_scan/Nmap及六个HTTP工具在原环境完成回环验收，gowitness以gorod实际PNG为准。下表保留2026-10-11实跑覆盖基线，涉及“缺WSL”和新工具“未接”的旧状态均被本段及TOOL_INTEGRATION的最新证据替代，不能据此重装发行版或套用旧工具标签。

默认入口为工作台项目列表，模式策略来自 `profiles/modes.yaml`，项目 YAML 单独保存权限、调查/核实/扩展范围、工具与参数。执行源 live/replay、权限预设和报告模板分别配置。运行快照固定原计划与参数，后续动作复核当前提交的权限及范围。

## 能力清单

验证文件均在 `data/validation/workbench-20261011/`，表中的“本地实跑”只指自有 loopback fixture；“离线”包括保存证据与替身响应。任何外部提供商均未进行本次联网验收。

| 功能 | 当前执行入口 / 工具 | 当前证据 | 尚缺的覆盖或依赖 |
|---|---|---|---|
| search | workbench_tools.search，六家既有引擎独立步骤 | multi-source.xml、fofa-workbench.xml：替身多源、失败降级、分页/重试配额 | 外部白名单、提供商真实响应；不读取现有秘密做开发验证 |
| company_lookup | passive_tools.company_lookup，股权/工商/备案导出文件 | passive-tools.xml：实际文件解析、公司起手式到报告/恢复 | 自主工商与备案 API 尚未接入；缺导出则 blocked |
| passive_subdomains | passive_indexes.passive_subdomains：CT、archive、subfinder、OneForAll saved exports | passive-integrated.xml：索引替身、去重、独立源、零目标DNS/HTTP | subfinder 实跑缺WSL；OneForAll统一live job未接入；更多公开源待补 |
| osint | Sourcegraph metadata流、保存SSE、招标导入 | passive-tools.xml：源health/截断/候选、真实文件与MockTransport | Sourcegraph外网未验收；未保存潜在代码秘密内容 |
| passive_supply_chain | saved_supply_analysis，已有公司/证书/供应商/邻域候选关联 | passive-tools.xml：关系维度/范围外隔离 | 证书、邻近IP、主体反查索引反馈尚未完整接入 |
| dns_recursive | active_tools.dns_recursive，显式resolver/dnspython | plan-dns-current.xml：多记录、多上游、CNAME、fake-IP；本地实跑 | dnsx/dig候选工具未接；公网DNS未验收 |
| tcp_scan | python_socket显式原生；Nmap/Masscan独立适配 | 本地native run；scan-batches-fixed.xml的Nmap参数/恢复为Mock | Nmap/Masscan实跑缺WSL，不能静默改用socket |
| service_probe | Nmap -sV独立，默认使用既有开放端口 | active工具替身断言 | 实跑缺WSL；脚本需独立deep_service_probe权限和approved_probes |
| web_visit | target_http，基础GET，不隐式运行路径/截图 | local-acceptance、UI、M5：本地真实HTTP | 公网/内网白名单实跑待授权 |
| tls_inspect | native_tls，显式IP或localhost，不隐式解析域名 | active工具本地TLS证书/协议观测 | 非本地TLS未验收；握手观测不等于完整协议/密码套件枚举 |
| screenshot | Playwright逐请求范围/物理预算，阻止service worker/download/websocket | 真实PNG/UI；m5-login-current.xml：独立login URL、实际password input识别 | 不提交账号密码；无登录form不冒充登录截图 |
| dns_enum | dnspython_dictionary，字典checkpoint冻结、stable wildcard baseline、workers | plan-dns-current.xml：真实本地并发/预算/恢复/取消 | 公网字典枚举未验收 |
| udp_scan | python_socket显式原生；Nmap独立UDP | 真实local echo与无响应分类；Nmap替身 | Nmap真实UDP缺WSL；无响应保持open_or_filtered/未知 |
| deep_service_probe | Nmap明确脚本白名单 | active工具替身权限/参数/取消 | 实跑缺WSL；planned_service_plugins未接 |
| web_crawl | native_crawler，规范URL/去重/深度/每host与全局预算 | m5-native、m5-login-current.xml：本地真实爬取/恢复 | planned_crawler未接；范围外只记录，不跟随 |
| js_analysis | native_js_analyzer，文件数/流式字节预算/候选端点 | m5-native、m5-login-current.xml：本地真实JS | 不自动核实端点；planned_js_analyzer未接 |
| web_path_enum | stage_7_paths独立，固定或配置字典/稳定随机基线 | local-acceptance、M5本地HTTP | planned_dictionary_adapter未接 |
| exposure_check | stage_7_exposure，批准检查类别与响应证据 | local-acceptance本地候选 | 更完整暴露插件待补；候选不能报告为已核实漏洞 |
| vulnerability_check | native_risk_checks：security_headers、cors_policy | m5-native本地实跑，review候选 | 通用风险插件/更多检查类别待接，planned runner未接 |
| takeover_probe | 批准provider HTTP marker +已有CNAME证据 | m5-native本地fixture，候选 | 不申领外部资源、不暗中DNS；真实provider环境待授权 |
| auth_audit | native_auth_audit：明确受保护路径的匿名访问观察 | m5-native本地401/公开/redirect用例 | 凭据认证及弱口令专项扩展未接；不继承基础Web权限 |

## 运行、证据与交付

| 契约 | 实现与实际证据 |
|---|---|
| 启动前计划 | GET项目plan/前端预览：有效工具、参数、权限、范围、预算、哈希；本地WSL/Chromium/dnspython依赖提示；不启动工具或读取凭据。plan-dns-current.xml与最新UI验证初始队列一致。反馈后新增步骤单独留痕。 |
| 工具痕迹与事件 | tool-calls.jsonl直接来自权威事件；SSE重连带cursor并去重；UI与磁盘条数/字段一致。 |
| 物理请求与配额 | 每HTTP跳转/browser子请求原子保守收费；完成receipt复用不收费，失败不退；FOFA每次物理请求/重试经过共享账户账本，15秒/200日上限。replay不使用真实账本。 |
| 控制与恢复 | OS运行租约、跨进程状态锁、持久动作receipt和feedback outbox。restart-20261011_110836_632889/summary.json：真正杀服务/重启/原run恢复，完成请求与事件不重复、资产不重复、撤权不恢复、账本不重置、旧exports与evidence hash不变。 |
| 双报告 | 同一规范快照：专业CSV/HTML/MD+11分类表各三格式，用户CSV精确七列及HTML/MD；schema asm.snapshot.v1/template asm.dual-report.v2。 |
| 部分/停止/中断/失败 | 状态与覆盖忠实保留。UI实际诱发自身fixture导出失败，旧snapshot保留且incomplete可见，恢复写入后重新导出清除错误。 |
| 证据包 | 所选snapshot的报告/共享证据/审计截止日志/账本备份ZIP，先验hash、缓存校验复用；不混入后续日志、不修改旧snapshot。bundle-plan-api.xml、review-bundle-current.xml及最新UI下载验证。 |
| 人工复核 | review_status与corroboration_status分别保存；佐证需选择至少两条匹配且独立来源证据，校验来源/文件hash，并明确人工判断。保持confidence/verification/ownership/permissions独立；excluded单列不混主表；重复提交幂等，原生更新不覆盖复核。 |
| 历史差异 | 匹配原计划+当前权限/范围、旧snapshot hash有效才比较新增、未再次观测、字段/证据变化。未再次观测不证明资产移除或风险修复。 |

最新综合回归：`unit-local-review-bundle-final.xml` 302通过（早于最新扫描分批修改）；新增扫描专项见`scan-batches-fixed.xml`。最新UI `ui-20261011_112731/summary.json` 49检查通过，无外网/settings访问。历史保留包的原run离线恢复在`replay-acceptance-20261011_111806_169195.json`通过，零新网络/秘密读取/配额变化。最终状态与后续最新证据仍以本地接力文档§10为准。

## 下一轮仍需实施

1. IP入口的PTR/whois/ASN归属、明确授权查询词和证书/IP邻域索引反馈；维持范围外不自动展开。
2. 补完整公开子域来源与统一OneForAll被动job，维持其隔离/flags禁主动/检查点/无旧job在线恢复绕过。
3. 工商备案自动提供商、更多风险与认证扩展、六源账户验证能力逐项实现；未支持方案明确blocked，不补假结果。
4. 外部测试授权、凭据和扫描工具依赖缺失属于实际阻塞；继续推进Mock、本地fixtures与页面功能，不能将外部未验收计为产品总验收通过。

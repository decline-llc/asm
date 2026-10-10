# 验收状态

2026-10-10，Session 003。完整完成定义仍为原设计第 10 章；不可把接口存在或 fixtures 回放当作实网验收通过。

| 项目 | 当前证据 | 状态 |
|---|---|---|
| Windows / WSL 架构 | PowerShell Core 7.6.5、Windows .venv Python 3.11.9、既有 Ubuntu 24.04 WSL2 | 已验证；发行版版本有差异 |
| 静态检查 | ruff 当前全绿 | 已通过 |
| 单元与集成 | 最新完整 `ASM_TEST_WSL=1 pytest` 35 passed in 44.72s；XML 在 data/validation/pytest.xml，0 failures/errors/skipped | 已通过，无 skip |
| 模糊资产隔离 | 单元与报告测试：D 级不进入 assets/总表 | 已通过 |
| FOFA 硬限速 | 实际 MockTransport 两次请求间隔 >=15s；超配额零请求 | 已通过 |
| 本地 HTTP | 全部注入路由发现、catch-all 区分、跳转越界先阻断 | 已通过 |
| 截图及报告 | Windows Playwright PNG、相对行号链接、8 sheet 字段契约；Artifact Tool 只读渲染并逐页检查八张表 | 逻辑与视觉核验通过 |
| WSL 工具部署 | 八二进制 SHA-256、Chrome、wafw00f、OneForAll 导入及固定 commit SecLists 所需字典；installed.txt 已生成 | 所需工具安装通过；SecLists 为稀疏检出 |
| 真实 WSL/nmap | 完成/失败 marker、二进制 tar、root nmap 3 TCP + 1 UDP ；本地 CLI 4 assets / 14 URLs / 13 routes | 已通过 |
| DNS 多上游 | WSL dnsx/dig 实际查询三组回环服务，五类记录、两跳 CNAME、CDN 指纹、0.0.0.0/fake-IP 隔离、优先地址交给 Stage 6 | 本地真实工具已通过 |
| DNS 复核与异常 | Windows 指定 IP:port 上游 A/AAAA/NXDOMAIN/超时；WSL CNAME 环路、最大跳数、恰好上限终止、悬空、超时；同上游不同来源不混入扫描结果 | 已通过 |
| DNS 报告与接管 | 域名 sheet 使用 selected，失败时不回退旧地址；可选 HTTP 指纹保存匹配文本/响应摘要；被动模式不探测 HTTP、CNAME/NXDOMAIN 单独不生成 takeover | 报告逻辑及模拟 HTTP 通过；公网待实测 |
| 18/18 doctor | Session 002 最终 exit 0，18 项全部通过；data/validation/doctor.json；本批未改工具安装 | 既有验收保持有效 |
| 自有域名被动链路 | 未提供书面授权的实网测试域名/API keys；只跑离线/本地 | 待真实输入 |
| 全方法覆盖 | 基础可运行；见后续 COVERAGE.md 的明确缺口 | 不能宣称 v2.0 全项完成 |
| GitHub | 本批准备推送 main，代码 CI 结果将在本文件追加；Session 002 四环境 CI [37921900265](https://github.com/decline-llc/asm/actions/runs/37921900265) 已通过 | 本批远端核验进行中 |

`ruff` 与 `pip check` 全绿，sdist 和 wheel 构建成功。wheel 仅包含 Python 包，运行 profiles/fixtures/init-wsl 仍需仓库 editable 安装。

本批 DNS 脱敏证据保留在 data/validation/dns/multi-resolver/ 和 negative-cases/，不提交 Git。环境通过不代表实网资产验收完成。系统 DNS 当前仍存在代理 fake-IP；Stage 5 已使用配置的显式上游并隔离不可用地址，公共上游可达性、真实 CDN/归属及接管仍需自有目标现场验证。SecLists 默认只安装版本锁列出的所需文件；完整检出由用户显式选择。

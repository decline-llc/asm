# 验收状态

2026-10-10，Session 006（CSV/独立 HTML 报告与工具 reference）。完整完成定义仍为原设计第 10 章；不可把接口存在或 fixtures 回放当作实网验收通过。

| 项目 | 当前证据 | 状态 |
|---|---|---|
| Windows / WSL 架构 | PowerShell Core 7.6.5、Windows .venv Python 3.11.9、既有 Ubuntu 24.04 WSL2 | 已验证；发行版版本有差异 |
| 静态检查 | ruff 当前全绿 | 已通过 |
| 单元与集成 | 最新完整 `ASM_TEST_WSL=1 pytest` 60 passed in 69.22s；XML 在 data/validation/report-formats-full.xml，0 failures/errors/skipped，含 9 项真实 WSL 验证 | 已通过，无 skip |
| 模糊资产隔离 | 单元与报告测试：D 级不进入 assets/总表 | 已通过 |
| FOFA 硬限速 | 实际 MockTransport 两次请求间隔 >=15s；超配额零请求 | 已通过 |
| 本地 HTTP | 全部注入路由发现、catch-all 区分、跳转越界先阻断 | 已通过 |
| 截图及报告 | Windows Playwright PNG；xlsx 八表字段与样式保持，CSV 总表/七明细与 xlsx 逐项一致；UTF-8 BOM、公式前缀转义、空表与截图缺失/无权限/非 PNG 明确处理 | 已通过 |
| 独立 HTML | 八表、全表搜索、CSP、HTML 转义、PNG 内嵌；单文件移动后离线/禁用 JS 均显示真实截图，零外部 HTTP 请求与页面错误；真实 test 样例首页/截图版式已检查 | 逻辑、离线与视觉核验通过 |
| 报告顺序与 reference | 默认 Stage 8 在 p1/p2 后，供应链待办进入导出；26 个 reference 文件链接检查通过，原生帮助保留本地 | 已通过；仅安装工具仍未自动接入 |
| WSL 工具部署 | 八二进制 SHA-256、Chrome、wafw00f、OneForAll 导入及固定 commit SecLists 所需字典；installed.txt 已生成 | 所需工具安装通过；SecLists 为稀疏检出 |
| OneForAll 调度 | 原生固定版本七个模块、SQLite/JSON 导出，离线 HTTP transport；阻断 socket 后无网络尝试；子 root 保留、七来源合并、双端点结果、不同 root 隔离、成功复用、空响应、503、模块/任务超时及重试 | 真实工具流程已通过；公网可达性/覆盖率待验证 |
| Stage 4 范围与失败出口 | OneForAll 后台提交、现有来源合并、root/全局范围双过滤、SaaS 排除；未导入上游未验证 IP/端口；部分失败保存其它有效结果及 review；dry-run/target-local 不启动工具 | 已通过 |
| 真实 WSL/nmap | 完成/失败 marker、二进制 tar、root nmap 3 TCP + 1 UDP ；本地 CLI 4 assets / 14 URLs / 13 routes | 已通过 |
| DNS 多上游 | WSL dnsx/dig 实际查询三组回环服务，五类记录、两跳 CNAME、CDN 指纹、0.0.0.0/fake-IP 隔离、优先地址交给 Stage 6 | 本地真实工具已通过 |
| DNS 复核与异常 | Windows 指定 IP:port 上游 A/AAAA/NXDOMAIN/超时；WSL CNAME 环路、最大跳数、恰好上限终止、悬空、超时；同上游不同来源不混入扫描结果 | 已通过 |
| DNS 报告与接管 | 域名 sheet 使用 selected，失败时不回退旧地址；可选 HTTP 指纹保存匹配文本/响应摘要并进入 todos；被动模式不探测 HTTP、CNAME/NXDOMAIN 单独不生成 takeover；追加定向回归 11 passed in 2.68s | 报告逻辑及模拟 HTTP 通过；公网待实测 |
| 18/18 doctor | Session 005 重测 exit 0，18 项全部通过；data/validation/doctor-current.json；未改工具安装 | 已重新验证部署；不证明 DNS 可信 |
| 两端公网 HTTPS | GitHub/PyPI/FOFA/Quake/crt.sh/CertSpotter 主页无凭据 HEAD，Windows/WSL 都有 HTTP 响应 | 抽检传输可达；认证 API/查询覆盖率未验证 |
| 两端公网 DNS | 系统及三个显式公共上游 UDP/TCP 53 都返回 example.com=198.18.0.122；HTTPS DNS 对照得公网地址，Windows 曾超时后成功 | 实网可信解析未通过；显式上游仍受 fake-IP 影响 |
| 自有域名被动链路 | 未提供书面授权的实网测试域名/API keys；只跑离线/本地 | 待真实输入 |
| 全方法覆盖 | 基础可运行；见后续 COVERAGE.md 的明确缺口 | 不能宣称 v2.0 全项完成 |
| GitHub | 上批代码 `019f6e4` 的四环境 CI [38018126858](https://github.com/decline-llc/asm/actions/runs/38018126858) 4/4 success；本批 CSV/HTML 变更的推送和新 CI 结果随后记录 | 本机验收通过，新代码远端验收待完成 |

`ruff` 与 `pip check` 全绿，sdist 和 wheel 构建成功。wheel 仅包含 Python 包，运行 profiles/fixtures/init-wsl 仍需仓库 editable 安装。

Session 006 原有构建 venv 缺少 wheel 且 setuptools 65.5.0 未达到 >=68，`build --no-isolation` 未通过；标准隔离 `python -m build` 成功，不修改项目运行依赖。构建输出在 data/validation/report-formats-dist/。test 报告实际导出总表 4、equity 1、domains 1、ips 1、urls 14、systems 1、social 0、todos 14，1 张首页截图；HTML 检查摘要位于 data/validation/report-formats-preview/checks.json。这些是本地回环数据，未扫描企业公网目标。

DNS 脱敏证据保留在 data/validation/dns/multi-resolver/ 和 negative-cases/；OneForAll 原生离线运行文件在 data/validation/oneforall/，均不提交 Git。Session 005 的 doctor 与 Windows/WSL 网络、HTTPS DNS 对照保存在 data/validation/，详见 OPERATIONS.md。环境通过不代表实网资产验收完成；两端公共 53 端口实测仍返回 fake-IP，Stage 5 过滤后可能无 selected，需建立可信解析路径。真实 CDN/归属、接管及带账户 API 仍待验证。OneForAll 核心测试未访问公网提供商；主页 HEAD 抽检也不证明其七来源接口完整可用。SecLists 默认只安装版本锁列出的所需文件；完整检出由用户显式选择。

# 运行配置

业务、测试和演示配置现在分别保存在 `investigations/`、`validation/`、`demo/`。详见 [项目整理说明](../docs/PROJECT_ORGANIZATION.md)。本文以下旧根目录路径可按短配置名继续使用。

- `modes.yaml`：三个预设 `passive_discovery`、`authorized_verify`、`full_asm`，能力目录、默认计划、工具参数和固定双版报告契约。Workbench 已实际消费这些字段。
- `local-lab-full.yaml`：自有回环 fixture 配置，项目 `lab_full`，TCP `8765,8766,8768`、UDP `8767`、HTTP `127.0.0.1:8765` 和截图。明确选择 Nmap；当前机器缺少 WSL 发行版，不能把模板或原生替代工具的测试算成 Nmap 实跑通过。
- `local-allowlisted-full.yaml`：待批准的白名单模板。总授权关闭、范围为空、批准依据和时间窗待填；各功能 `allow:true` 只是拟申请清单。
- `default.yaml`、`demo.yaml`、`test.yaml`：旧 schema1 模板与兼容测试。新产品配置使用 schema2。

`mode_preset` 决定可选能力，`execution.source: live|replay` 决定执行来源，`reports` 决定报告模板与表现参数，三者独立。全面模式包含被动收集、DNS、TCP/UDP、服务、Web/TLS、截图、爬取、JS/路径和暴露风险核查；专项认证检查需单独配置。

Workbench 按通用默认→模式默认→项目覆盖解析工具与普通参数；权限默认拒绝。执行同时要求模式支持、计划选中、项目权限、对应范围、授权窗、工具依赖和预算有效。调查范围、主动核实范围、深入范围分别配置。手动加入调查范围不会授予主动测试权限；恢复使用原运行计划、工具和参数，并复核当前有效权限，不恢复已撤销的权限。

项目表单通过本地 API 保存 `profiles/<分类>/local-<project>.yaml`。文件不含凭据，分类目录中的 `local*.yaml` 被 Git 忽略，必须随本地接力保留。新运行在 `report/<分类>/<project>_delivery/runs/<run_id>/`，保存脱敏有效配置、检查点、事实、日志和独立导出快照；专业版与用户版各 CSV/HTML/Markdown，旧证据与旧导出不覆盖。权威业务项目/运行状态在 `data/workbench.sqlite`，后续验收状态在 `data/validation/workbench.sqlite`，账户配额在 `data/account-rate-ledger.sqlite`。

在 PowerShell 7 中启动工作台：

```powershell
.\.venv\Scripts\python.exe -m asm serve --port 6400
```

打开 `http://127.0.0.1:6400`，新建项目、编辑逐功能权限和工具参数，然后启动。已有项目可在前端查看实际状态、原始输出、文件树与报告；`?demo=1` 是虚构演示，`?pilot=1` 是已有历史证据浏览。

fixture 就绪且所选工具可用时执行本地项目：

```powershell
.\.venv\Scripts\python.exe -m asm workbench-run --profile local-lab-full --source live
.\.venv\Scripts\python.exe -m asm workbench-run --profile local-lab-full --resume <原run_id>
```

CLI schema2 的 `run` 也转接统一 Workbench；旧阶段编号仅映射到项目计划中已选能力，不绕过新策略。replay/dry-run 已加固为离线执行，缺证据如实 partial，不在线回退；真实目标历史包只能使用已有证据。

本地真实 TCP/UDP、DNS并发/TLS、HTTP、独立登录页截图、爬取/JS、路径/暴露、有限header/CORS/接管与匿名保护路径核查已验证。真实后端进程kill/重启/原run恢复、撤权/账本/完成动作不重复、双报告与UI已验证。启动前可预览执行计划和本地依赖提示，支持持久人工复核及按冻结快照下载完整证据包；复核/佐证不自动改变归属、核实状态或权限。Nmap/Masscan分批参数与取消/恢复仅Mock，实跑受WSL缺失阻塞。公司/备案目前导出导入、Sourcegraph替身、供应链已有证据分析；自动工商API、完整关联查询、OneForAll live job和更广专项插件仍未完成。逐项覆盖见 `docs/WORKBENCH_CAPABILITIES.md`，最新验收与下一步见本地接力§10。

批准白名单后才填写实际域名/IP、独立功能范围、批准依据和有效时间窗，另存项目再运行。外部被动验收也需用户确认测试输入。API 凭据仅由后端设置或根 `.env` 管理，禁止写入 YAML、前端、报告或日志。

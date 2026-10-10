# ASM Workbench（编排 CLI 与报告）

> 状态：**已自动调用（主流程入口）**
> 版本：`asm-workbench 0.1.0`（仓库 editable 安装）；Python 3.11.9
> 核对日期：2026-10-10（回环实测：`scripts/local-demo.py` 与 60 项回归通过，见 ACCEPTANCE）
> 证据：本机源码 [cli.py](../../asm/cli.py)、[pipeline.py](../../asm/pipeline.py)、[s8_report.py](../../asm/stages/s8_report.py)

## 1. 用途、场景与局限

- **用途**：Windows 侧编排入口。读取 profile/.env，调度 WSL 原生工具与各阶段，把结果标准化入库（SQLite `asm.db`），并导出八表报告（XLSX/CSV/HTML）。
- **适用场景**：项目级暴露面采集的全流程（`run`）、单阶段重跑（`stage`）、部署自检（`doctor`）、新机器 WSL 安装（`init-wsl`）、仅重导出报告（`report`）、查询 API 配额账本（`quota`）。
- **局限**：不是扫描器本身；端口/服务识别依赖 WSL nmap/masscan，HTTP 探测用 Windows Python httpx 库，截图用 Windows Playwright。**没有通用 `asm ingest`/`asm search` 命令**，人工运行工具产生的文件不会自动入库；搜索引擎只有 FOFA/Quake 进入主流程（见 api.md 与各引擎专页）。CLI 对 failed/partial 阶段返回非零，但已有有效结果保留，不能把非零理解为“全部数据无效”。
- **安装位置**：`D:\Desktop\asm\.venv\Scripts\python.exe -m asm`（Windows）。WSL 工具在 `/home/longchuanli/asm-ws`，经 stdin/tar 管道交换，不直接读写 `/mnt/d`。

## 2. 实际接入状态

| 子命令 | 作用 | 是否发网络请求 |
|---|---|---|
| `doctor` | 18 项部署自检 | 不访问带账户 API；只做本地/安装检查 |
| `init-wsl` | WSL 工具安装/校验 | 下载固定版本（新机器）；本机已装，不用重复 |
| `run` / `stage` | 流水线编排 | 按阶段访问目标/公开来源/已配置 API |
| `report` | 从已有数据库重导出三格式 | 不重新采集 |
| `quota` | 打印 sources 配额账本 | 不发网络请求 |

## 3. 场景命令（PowerShell 7，仓库根目录 `D:\Desktop\asm`）

> 前置：已创建 `.venv` 并 `pip install -e .[dev,browser]`；新机器另需 `python -m playwright install chromium`。除 doctor/quota 外，多数命令要求先建好 `profiles/<name>.yaml`。

```powershell
# 环境自检（不发账户 API）；失败时退出码为 1，逐行给出 Repair 提示
.\.venv\Scripts\python.exe -m asm doctor
.\.venv\Scripts\python.exe -m asm doctor --json-output

# 首次部署 WSL 工具；本机已安装，仅在重装/新机器时运行
.\.venv\Scripts\python.exe -m asm init-wsl --distro Ubuntu

# 完全离线 fixture 演示：独立 dry-run 数据库，不采集公网
.\.venv\Scripts\python.exe -m asm run --profile demo --stages 1,2a,2b,3,4,5,p1,p2,8 --dry-run --passive-only

# 本地真实回环：端口、Web、截图、三格式报告（自带 fixture）
.\.venv\Scripts\python.exe scripts/local-demo.py

# 已配置 customer 后的基础被动域名/DNS 链路（不触发主动 6/7 阶段）
.\.venv\Scripts\python.exe -m asm run --profile customer --stages 1,3,4,5,8 --passive-only

# 完成主动范围与可信解析后，完整项目顺序；--resume 跳过同配置已完成阶段
.\.venv\Scripts\python.exe -m asm run --profile customer --stages 1,2a,2b,3,4,5,6,7,p1,p2,8 --resume

# 仅从既有数据库重导出，不重新扫描
.\.venv\Scripts\python.exe -m asm report --profile customer
# 指定同一套导出的基名；.xlsx/.csv/.html 任一后缀都会生成三格式
.\.venv\Scripts\python.exe -m asm report --profile customer --output data/customer/delivery.html

# 查询各搜索引擎当日已用/配额；不发请求
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

| 命令 | 运行环境 | 前置条件 | 关键参数 | 输出位置 | 预期结果 | 失败判定 |
|---|---|---|---|---|---|---|
| `doctor` | Windows | 已装 .venv/WSL | `--json-output` 机读 | stdout / `data/validation/doctor-current.json`（手动保存） | 18/18 PASS，exit 0 | 任一 FAIL 或非零退出；按 Repair 处理 |
| `run` | Windows+WSL | profile+授权/范围 | `--stages`、`--passive-only`、`--dry-run`、`--resume`、`--target-local` | `data/<profile>/`、`logs/pipeline.jsonl` | 各阶段 completed，报告生成 | 任一 failed/partial 时整体 exit 1；`pipeline.jsonl` 记录 notes |
| `report` | Windows | 已有 `asm.db` | `--output`（三后缀） | `data/<profile>/report.*`、`report-csv/`、`screenshots/` | 三格式与八表生成，计数一致 | 无数据库时报 “No project database; run collection first” |
| `quota` | Windows | 已有 `asm.db` | — | stdout JSON | 列出 sources 表 | 数据库缺失则报错 |

**阶段与顺序**：默认 Stage 8 已排在 p1/p2 之后；自定义 `--stages` 时也应把 `8` 放最后（`...,p1,p2,8`）。`--passive-only` 或未授权时，6/7 主动阶段被拒绝（显式指定会抛 ScopeError）。`--resume` 只跳过同配置指纹下已 completed 的阶段；工具级成功缓存（job 幂等）是另一层，需全新采集时用新 profile/输出库。`--target-local` 限定回环，WSL NAT 与 Windows 回环不同，fixture 分别部署。

## 4. 输出格式与解析

- **编排产物目录**：`data/<profile>/asm.db`（唯一事实源）、`stages/<stage>/*.json`（阶段证据）、`results/<stage>/<jobid>/`（WSL 回收的原始结果、输入、runner、job.log、rc/done）、`logs/pipeline.jsonl`、`logs/bridge.jsonl`。
- **报告三格式**（Stage 8 / `asm report` 同源生成）：
  - `report.xlsx`：八 sheet，截图列是相对路径 `screenshots/<序号>.png`，需连同 `screenshots/` 一起交付。
  - `report.csv`（总表）+ `report-csv/*.csv`（七明细）：UTF-8 BOM，逗号/双引号/换行由 csv writer 处理；以 `=` `+` `-` `@` 开头或前导空白后出现这些字符的文本统一加 `'` 前缀，防止被 Excel 当公式。
  - `report.html`：八表 + 全表搜索 + 内嵌可读取 PNG（data URI），含 CSP 与 HTML 转义；单独搬走、离线、禁用 JavaScript 仍可阅读表格与已采集图片。**未采集/缺失/无法读取的截图会被明确标注，报告不能恢复未采集的截图**。
- **解析方法**：SQLite 是事实源，可用标准库只读打开：`python -c "import sqlite3;print(sqlite3.connect('file:data/<profile>/asm.db?mode=ro',uri=True).execute('select host,port,proto,service,source from assets').fetchall())"`。pipeline 日志是 JSONL，逐行解析。

## 5. 结果衔接与入库

- 编排输出 `asm.db` 是下游一切（report、人工 SQL 复查、quota）的输入；外部工具只有经对应 Stage/适配器解析后才入库。
- `asm report` 不再触发采集；`asm run` 的 Stage 8 与独立 `report` 共用同一组行。
- 人工用 WSL 工具产生的 JSONL/文本放在 `results/manual/...`，**不会自动进入当前 SQLite/报告**；要入库需另写适配器或走正式 Stage。

## 6. 去重、来源与复核

- 数据库去重键见 [README 索引](README.md) 与 OPERATIONS.md §7：资产 `(host,port,proto)`、域名标准化、URL 原样、review `(kind,url,evidence)`、DNS `(domain,rtype,value,resolver)`。同键 sources 合并取并集。
- 阶段状态、任务指纹、配额账本都在库内；`--resume` 依据 `pipeline_state` + 配置指纹。
- 独立复核：`jobs` 表查 rc/status/log_path；`asm quota` 核 API 账本；`data/<profile>/stages/*/…json` 对照原始结果目录。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 报告缺支路结果 | 检查显式 `--stages` 是否把 8 放最后，或采集后用 `report` 重导出 |
| 主动阶段被拒绝 | 核对 profile `authorization: true`、非 passive、域名/IP 两类范围都批准 |
| xlsx 截图链接失效 | 确认 `screenshots/` 与 xlsx 一起交付；独立 HTML 已内嵌图片 |
| HTML 无截图 | 区分“未采集（被动模式/非 Web/失败页）”“文件缺失”“非 PNG/读取异常”；报告不能重建未保存图片 |
| `--resume` 仍重跑 | 配置或模式指纹变了；全新采集用新 profile/输出库 |
| exit 1 但有数据 | failed/partial 阶段存在；看 `logs/pipeline.jsonl` 与 jobs 表，有效结果仍保留 |
| 数据库被占用复制不完整 | 等运行结束关闭数据库后再复制，避免只复制未合并 WAL 的活动库 |

## 8. 官方来源与核对记录

- 依据源码：[cli.py](../../asm/cli.py)、[pipeline.py](../../asm/pipeline.py)、[s8_report.py](../../asm/stages/s8_report.py)、[report_html.py](../../asm/report_html.py)、[db.py](../../asm/db.py)。
- 运行手册 [RUNBOOK.md](../RUNBOOK.md)、操作说明 [OPERATIONS.md](../OPERATIONS.md)、验收 [ACCEPTANCE.md](../ACCEPTANCE.md)。
- 回环实测证据：`data/validation/local-demo.json`、`data/validation/report-formats-full.xml`（60 passed）、`data/validation/report-formats-preview/checks.json`。
- 待验证：真实授权域名的完整主动链路、带账户搜索引擎、可信解析路径建立后的实网采集。

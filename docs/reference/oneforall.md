# OneForAll（被动子域收集，隔离包装）

> 状态：**已自动调用**（Stage 4，经项目隔离包装器）
> 版本：v0.4.5，固定 commit `5ad26a99cd8625dfff0f3ce0300a10b38135b03a`（见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/tools/OneForAll`，独立 venv `~/asm-ws/tools/OneForAll/.venv/bin/python`
> 核对日期：2026-10-10（回环/离线实测：真实七模块+SQLite/JSON 导出通过，见 ACCEPTANCE）
> 证据：包装器 [tools/oneforall_runner.py](../../tools/oneforall_runner.py)、调度 [asm/stages/oneforall.py](../../asm/stages/oneforall.py)、离线证据 `data/validation/oneforall/`

## 1. 用途、场景与局限

- **用途**：从公开被动来源收集 root 下子域。本项目**不直接运行上游默认 `run/main` 全流程**，只用 `tools/oneforall_runner.py` 调度的 Collect + 原生 SQLite/JSON 导出路径。
- **为什么隔离**：固定 v0.4.5 主流程即使关闭 brute/dns/req，仍会触发 wildcard/SRV 查询并把目标扩到父注册域；包装器精确保留授权 root、关闭这些行为，且不修改第三方源码。
- **局限**：白名单仅 7 个公开被动来源（默认 5 个）；**不**做目标探测、DNS 解析、爆破、付费 API；工具自报的 IP/80 端口**不作为**资产事实（解析统一交 Stage 5）。公网提供商可达性与已知子域覆盖率**待真实输入验证**。
- **接入状态**：Stage 4 后台任务调用，幂等缓存；人工不能直接跑上游默认流程，只能用同一包装器。

## 2. 实际接入状态与配置

调度：`oneforall.submit()` 把 `oneforall_runner.py` + `oneforall_support.py` + 计划 JSON 经 stdin 写入原生任务目录，用独立 venv 执行；HTTP 经进程内 guard 限定“各模块公开主机、仅 GET/HEAD、关闭重定向、TLS 验证、响应 ≤8 MiB”。

profile 生效配置（参与 `--resume` 指纹；默认值见 [RUNBOOK](../RUNBOOK.md)）：

```yaml
oneforall:
  enabled: true
  modules:           # 默认五项；另允许 crtsh、hackertarget
    - modules.certificates.certspotter
    - modules.datasets.rapiddns
    - modules.datasets.anubis
    - modules.intelligence.alienvault
    - modules.intelligence.threatminer
  module_timeout: 45      # 上限 300 秒
  request_timeout: 15     # 上限 60 秒
limits:
  oneforall_timeout: 3600
```

- `enabled: false` 临时关闭。`modules` 只能选这七个之一/子集，不能配置主动或付费模块。
- 凭据：白名单为公开来源，不传付费模块 key；第三方源码不改动。

## 3. 场景命令（PowerShell 7，仓库根目录）

```powershell
# 准备项目后的正常被动收集（Stage 4 一并跑 subfinder/公开来源/FOFA/Quake）
.\.venv\Scripts\python.exe -m asm stage 4 --profile customer --passive-only
# 干跑：不启动第三方工具
.\.venv\Scripts\python.exe -m asm stage 4 --profile demo --dry-run --passive-only
# 离线验证原生核心、来源合并、失败/缓存，不查公网
$env:ASM_TEST_WSL='1'
.\.venv\Scripts\python.exe -m pytest tests/unit/test_oneforall.py tests/integration/test_wsl.py -k oneforall -q
```

| 命令 | 运行环境 | 前置条件 | 关键参数 | 输出位置 | 预期结果 | 失败判定 |
|---|---|---|---|---|---|---|
| `stage 4 --passive-only` | Windows+WSL | profile 范围内 root | profile `oneforall.*`、`limits.oneforall_timeout` | `data/<profile>/results/4/<jobid>/`、`oneforall-evidence.json` | rc=0，accepted 入库 | rc=2 部分失败、rc=124 整任务超时 |
| dry-run | Windows | — | `--dry-run` | 独立 dry-run 库 | 不启动工具 | — |
| pytest 离线 | Windows+WSL | 测试依赖 | `-k oneforall` | `data/validation/oneforall/` | 12 passed，零网络尝试 | 断言失败/有 network_attempts |

**运行环境与超时**：原生 WSL 后台任务，外层 Linux `timeout`；模块线程各自 join，整任务受 `oneforall_timeout` 限制。RapidDNS 在该固定版本用 HTTP，若跳转或非 2xx，包装器**不跟随**并记 partial。

## 4. 原生输出格式与解析

每任务独立目录，含：

- `oneforall-observations.json`：**去重前**观测（JSON 数组），避免上游只保留首个来源。样例（脱敏）：

  ```json
  [{"subdomain":"api.authorized.invalid","source":"certspotter"},
   {"subdomain":"mail.authorized.invalid","source":"rapiddns"}]
  ```

- `oneforall.json`：原生**去重后**输出（JSON 数组）。
- `oneforall-run.json`：本次运行证据（mode、entrypoint、root、flags 全 false、模块状态、HTTP 事件、count、status）。
- `vendor-results/result.sqlite3`、各模块 JSON、`oneforall.log`、rc/done。
- 阶段汇总 `oneforall-evidence.json`：jobid、accepted/excluded/invalid、每模块状态与失败。

**解析方法**：`oneforall-observations.json` 用 `utf-8-sig` 读成 JSON 数组（不是 JSONL）；逐条校验 `subdomain` 在请求 root 内且全局白名单通过、`source` 匹配 `[A-Za-z0-9_-]{1,64}`，否则进 excluded/invalid。AlienVault 两端点在进程内取并集。

## 5. 结果衔接与入库

- 衔接：accepted 域名 → 与 subfinder 等来源合并 → Stage 5 解析。
- 入库：仅把**请求 root 下、白名单内**的域名入库 `domains`，来源 `oneforall:<模块名>`；工具产生的 IP/端口字段不入资产表。
- 人工放置的 OneForAll 文件不会被自动导入；成功任务在相同工具/参数/输入且结果目录仍在时可复用。

## 6. 去重、来源与复核

- 去重键：标准化完整域名；先导出去重前观测，保留每个来源。
- 来源保留：`oneforall:<模块>` 标签入 `domains.sources` 并集。
- 时间戳：框架任务与 JSON 证据含时间；任务目录 `job.log`、`rc`。
- 独立复核：核对 `oneforall-run.json` 的 flags 全 false、模块状态、HTTP 事件主机白名单；`data/validation/oneforall/index.json` 汇总离线验收 rc/状态且 network_attempts=0。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| rc=2 | 模块/HTTP 部分失败；其余来源结果仍保留并写 `oneforall_partial` review，不算完整成功 |
| rc=124 | 整任务超时；核对日志与 `oneforall_timeout` 后重试 |
| RapidDNS 跳转/非 2xx | 固定包装器不跟随，记 partial；不要手动改成跟随 |
| 缺 distutils / exrex 异常 | 检查独立 venv 的 setuptools 75.8.0 / exrex 0.12.0（版本锁），不改第三方源码 |
| 提交后没有采集 | 成功任务缓存可能复用；全新采集用新 profile/输出库 |
| 上游默认 run/main | **不要**直接执行；会触发 wildcard/SRV 与父域扩张，超出授权范围 |

## 8. 官方来源与核对记录

- 官方仓库核对：[shmilylty/OneForAll](https://github.com/shmilylty/OneForAll)；固定 commit 与 [tool-lock.json](../../tools/tool-lock.json) 一致（`git -C ... rev-parse HEAD` 由包装器核对，不一致即拒绝运行）。
- 本机证据：[tools/oneforall_runner.py](../../tools/oneforall_runner.py)、[asm/stages/oneforall.py](../../asm/stages/oneforall.py)、[asm/utils/oneforall.py](../../asm/utils/oneforall.py)；离线验收 `data/validation/oneforall/`、`data/validation/oneforall-ci.json`。
- 待验证：公网七来源实际可达性与覆盖率（需自有授权域名输入）；未做带凭据/付费来源验收。

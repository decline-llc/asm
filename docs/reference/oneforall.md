# OneForAll

固定 v0.4.5/commit 5ad26a99，位置 `~/asm-ws/tools/OneForAll`，独立 `.venv/bin/python`。Stage 4 已接入隔离被动包装器；不要直接执行上游默认 run/main 的全部模块。

```powershell
# 准备项目后的正常被动收集
.\.venv\Scripts\python.exe -m asm stage 4 --profile customer --passive-only
# 干跑：不启动第三方工具
.\.venv\Scripts\python.exe -m asm stage 4 --profile demo --dry-run --passive-only
# 原生核心及失败/缓存的离线验证，不查公网
$env:ASM_TEST_WSL='1'
.\.venv\Scripts\python.exe -m pytest tests/unit/test_oneforall.py tests/integration/test_wsl.py -k oneforall -q
```

场景参数在 profile：`oneforall.enabled: false` 临时关闭；`modules` 默认 CertSpotter/RapidDNS/Anubis/AlienVault/ThreatMiner 五项，另允许 Crtsh/HackerTarget；`module_timeout` 默认 45，`request_timeout` 默认 15，整任务 `limits.oneforall_timeout` 默认 3600。完整模块标识和配置见 [RUNBOOK](../RUNBOOK.md)。

保存去重前 oneforall-observations.json、去重后 oneforall.json、模块状态/日志、SQLite。只将请求 root 内域名和来源入库；工具 IP/80 端口不作为资产事实。用 evidence JSON 核对 accepted/excluded/invalid、每模块状态与失败。

| 情况 | 处理 |
|---|---|
| rc=2 | 模块/HTTP 部分失败，保留其它来源，不算完整成功 |
| rc=124 | 整任务超时，核对日志和上限后重试 |
| RapidDNS 跳转 | 固定包装器不跟随，记录 partial |
| 缺 distutils / exrex 异常 | 检查独立 venv 的 setuptools 75.8.0/exrex 0.12.0，按版本锁修复，不改第三方源码 |
| 未重新采集 | 成功任务缓存可能复用；全新项目库用于新的采集周期 |

依据：[包装器](../../tools/oneforall_runner.py)、[调度](../../asm/stages/oneforall.py)。

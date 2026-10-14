# 工具版本与集成状态矩阵

> 目的：把「本机装了什么版本」与「是否真的接入了流水线」收敛到一处可核对的地方。此前版本只记录在被 Git 忽略的 `data/validation/` 证据里，随环境变动会丢失；权威二进制版本仍以 [tool-lock.json](../../tools/tool-lock.json) 为唯一来源，本表与它的一致性由 `tests/unit/test_tool_reference_docs.py` 强制。
> 版本核对：2026-10-12（原 WSL 环境，`data/validation/original-wsl-tools-20261012.txt`）；集成状态核对：Session 009（2026-10-14，以代码为准）。
> 集成状态取值固定为下表几种，便于机器校验：`Stage 4`、`Stage 5`、`Stage 6`、`Stage 7/broker`、`人工`、`运行时依赖`、`未接入`。

| 工具 | 版本 | 集成状态 | 接入位置 | 证据 |
|---|---|---|---|---|
| subfinder | 2.17.0 | Stage 4 | Stage 4 被动子域（幂等缓存） | `data/validation/original-wsl-tools-20261012.txt` |
| OneForAll | v0.4.5 | Stage 4 | Stage 4 隔离 live job / 留档导入 | 同上；`data/validation/oneforall/` |
| dnsx | 1.3.1 | Stage 5 | Stage 5 每个 `dns.resolvers` 上游独立后台调用 | 同上；`data/validation/external-tools-20261012.xml` |
| dig_probe | util-linux（系统包） | Stage 5 | Stage 5 stdlib 包装器在 WSL 调 dig | 同上 |
| naabu | 2.6.1 | Stage 6 | Stage 6 TCP 发现可选引擎 | 同上 |
| a_scan | 项目脚本（哈希见证据） | Stage 6 | Stage 6 TCP 发现可选引擎（任务副本 + 哈希校验） | 同上 |
| httpx | 1.12.0 | Stage 7/broker | Stage 7 `web_visit`，经 broker 转交 Windows 请求 | `data/validation/external-tools-live-20261012-150458/summary.json` |
| ffuf | 2.3.0 | Stage 7/broker | Stage 7 `web_path_enum`（随机基线 + 二次复核） | 同上 |
| katana | 1.8.0 | Stage 7/broker | Stage 7 `web_crawl`（精确 crawl-scope、`-dr`、`-duc`、可选 `-jc`） | 同上；`report/validation/broker-scope-unit.xml` |
| gowitness | 3.2.0 | Stage 7/broker | Stage 7 `screenshot`（gorod 驱动 + 任务内 Chrome 代理） | `data/validation/external-tools-live-20261012-151602/summary.json` |
| nuclei | 3.11.1 | Stage 7/broker | Stage 7 `vulnerability_check`（仅仓库内批准 HTTP 模板） | `data/validation/external-tools-live-20261012-150458/summary.json` |
| wafw00f | 独立 venv（未在 tool-lock 固定） | Stage 7/broker | Stage 7 `vulnerability_check`（须显式选 `waf_fingerprint`） | 同上 |
| Chrome | gowitness 运行时依赖 | 运行时依赖 | 仅由 gowitness 以固定 SPKI 代理启动，不独立调度 | `data/validation/web-tool-help/gowitness.txt` |
| SecLists | 2026.1（commit 190c6f7…） | 运行时依赖 | DNS/内置路径/ffuf 的冻结字典输入 | `tools/tool-lock.json` |

## 约定与边界

- `Stage 7/broker` 表示：工具在仅有 loopback 的私有 network namespace 中运行，**没有直接目标网络出口**，每个请求（含重定向跳与浏览器子资源）都经代理交回 Windows 的 `ExecutionContext.http`，因此与内置采集共用同一授权范围、同一每主机物理预算与回执；越界主机 403 且不产生传输。详见 [TOOL_INTEGRATION.md](../TOOL_INTEGRATION.md) 与 [external_tools.py](../../asm/external_tools.py)。
- `人工` 表示只有手工命令参考，没有适配器（如 Amass、gau、waybackurls、LinkFinder、arjun、x8）。本表当前没有被标记为 `未接入` 的已接入工具；新增适配器时应同步更新本表。
- 版本列与 [tool-lock.json](../../tools/tool-lock.json) 的 `binaries[].version` 必须一致（测试强制）；该文件未固定的工具（nmap、masscan、wafw00f、Chrome、dig）按实际来源标注，运行时版本仍由每次外部执行的 `version` 回执记录在运行记录里。
- 本文件只描述**版本与接入事实**；每个工具的参数、输出解析、排错与官方来源见 `docs/reference/<tool>.md`。
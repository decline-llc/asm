# waybackurls（调研笔记，未安装）

> 状态：**尚未安装** — 本页为调研笔记；README 原文未能取得，**全部细节待安装后核对**
> 版本（官方，调研时）：最新 tag **v0.1.0**（2022-04-05，来源 [pkg.go.dev](https://pkg.go.dev/github.com/tomnomnom/waybackurls)）
> 预计位置：WSL `~/asm-ws/bin/waybackurls`（未安装）
> 核对日期：2026-10-10（仅版本/模块信息经 pkg.go.dev 核对；**README 未核验**）
> 证据：[pkg.go.dev/github.com/tomnomnom/waybackurls](https://pkg.go.dev/github.com/tomnomnom/waybackurls)、[GitHub 仓库](https://github.com/tomnomnom/waybackurls)

> ⚠️ 本工具 README 原文因网络受限**未能取得**；除“版本/模块”外，**所有用法均为待核对**，不在本文落任何具体参数。安装后以 `waybackurls --help` 与官方 README 重写本页。

## 1. 用途、场景与局限

- **用途**（定位）：tomnomnom 出品的 Wayback Machine 已知 URL 提取工具（gau 官方 README 称其为灵感来源，侧面印证用途）。
- **适用场景**：补充 Wayback Machine 的历史 URL 线索。
- **局限**：历史 URL 不代表当前存活；需 httpx 复核。
- **接入状态**：未安装；无调度。

## 2. 安装方式（待核对）

- 预计：`go install github.com/tomnomnom/waybackurls@latest`（**未核实**）。
- release/二进制发布情况：**未核实**。

## 3. 输入准备与场景命令（待核对）

- 输入/输出方式、并发、超时、代理、`-dates`/`-no-subs`/`-get-versions` 等参数：**一律以安装后官方 README 与 `--help` 为准**，本页不预写。

```bash
# 占位（未核验）：安装后按 --help 重写
# printf '%s\n' "$ROOT" | waybackurls > "$OUT/waybackurls.txt"
```

## 4. 输出与解析（待核对）

- 预计 stdout 行文本 URL；逐行解析，先范围过滤再按完整 URL 保留。

## 5. 结果衔接与入库（规划）

- 衔接：历史 URL → 范围过滤 → httpx 存活复核。
- 入库：不自动入库。

## 6. 去重与复核（规划）

- 去重键：完整 URL；与 gau/katana 对照；httpx 复核存活。

## 7. 常见失败（预期，待核对）

| 情况 | 处理 |
|---|---|
| 历史死链多 | 交 httpx 复核存活 |
| 参数未知 | 以安装后 `--help` 为准 |

## 8. 官方来源与核对记录

- 官方核对：[pkg.go.dev/github.com/tomnomnom/waybackurls](https://pkg.go.dev/github.com/tomnomnom/waybackurls)（版本 v0.1.0、模块信息）。
- 未覆盖：README 全文、参数、安装方式、release 发布情况（GitHub 抓取受限）。
- 待验证：安装与全部 CLI 细节。

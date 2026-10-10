# LinkFinder（调研笔记，未安装）

> 状态：**尚未安装** — 本页为调研笔记；README 原文未能取得，**全部细节待安装后核对**
> 版本（官方，调研时）：未见官方 release 体系（**未核实**）
> 预计位置：WSL `~/asm-ws/tools/LinkFinder`（Python 脚本形式，未安装）
> 核对日期：2026-10-10（**README 未核验**：GitHub 受限、PyPI 无此官方包、无官方文档站）
> 证据：[GitHub 仓库](https://github.com/GerbenJavado/LinkFinder)（唯一官方来源，本次未能抓取原文）

> ⚠️ 本工具官方 README 因网络受限**未能取得**；除“用途定位”外，**所有用法均为待核对**，不预写具体参数。安装后以官方 README 与 `python3 linkfinder.py --help` 重写本页。

## 1. 用途、场景与局限

- **用途**（官方描述定位）：在 JavaScript 文件中发现**端点及参数**（此描述本次未能从官方页面原文核验）。
- **适用场景**：对 katana/httpx 发现的 JS 文件做端点提取，补充爬取覆盖。
- **局限**：JS 中出现的链接/端点**不表示已存在服务**；需 httpx/人工复核。
- **接入状态**：未安装；无调度。

## 2. 安装方式（待核对）

- 仓库为 Python 脚本形式；通常 `git clone` + 安装依赖后 `python3 linkfinder.py` 调用（**未核实，以 README 为准**）。
- 依赖与 Python 版本要求：**未核实**。

## 3. 输入准备与场景命令（待核对）

- 输入（URL/本地 JS 文件/Burp 导出）、输出（cli/HTML）、参数：**一律以安装后官方 README 与 `--help` 为准**，本页不预写。

```bash
# 占位（未核验）：安装后按 --help 重写
# python3 linkfinder.py -i "$URL" -o cli
```

## 4. 输出与解析（待核对）

- 预计输出发现的端点/参数（文本或 HTML）；解析方式待核对。

## 5. 结果衔接与入库（规划）

- 衔接：gau/waybackurls/katana 发现的 JS → LinkFinder 提取端点 → httpx 复核。
- 入库：不自动入库。

## 6. 去重与复核（规划）

- 去重键：完整 URL/端点；与 katana 的 JS 端点对照；复核存活。

## 7. 常见失败（预期，待核对）

| 情况 | 处理 |
|---|---|
| 端点不存在服务 | 交 httpx 复核 |
| 参数/用法未知 | 以安装后 `--help` 为准 |

## 8. 官方来源与核对记录

- 官方核对：[GitHub 仓库](https://github.com/GerbenJavado/LinkFinder)（本次未能抓取原文）。
- 未覆盖：README 全文、安装、输入/输出、参数、版本（GitHub 受限）。
- 待验证：全部细节。

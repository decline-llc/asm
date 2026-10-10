# arjun（HTTP 参数发现，调研笔记，未安装）

> 状态：**尚未安装** — 本页为调研笔记，命令与参数**待安装后核对**（`arjun --help`）
> 版本（官方，调研时）：PyPI 最新 **2.2.7**（2024-11-03；2.2.3 已被官方 yank）（来源 [PyPI JSON API](https://pypi.org/pypi/arjun/json)）
> 预计位置：WSL `~/asm-ws/tools/arjun/.venv/bin/arjun`（未安装）
> 核对日期：2026-10-10（官方 README 经 PyPI 核对，**非本机验证**）
> 证据：[PyPI arjun](https://pypi.org/pypi/arjun/json)、[GitHub 仓库](https://github.com/s0md3v/Arjun)、[官方 Wiki Usage](https://github.com/s0md3v/Arjun/wiki/Usage)

> ⚠️ 本文内容来自官方 README 的**调研**（经 PyPI 取得），**未在本机验证**；具体 flag 名以安装后 `arjun --help` 与官方 Wiki 为准。

## 1. 用途、场景与局限

- **用途**：HTTP Parameter Discovery Suite，发现 URL 端点的**隐藏查询参数**；内置约 25,890 个参数名的默认字典，宣称 50–60 个请求、10 秒内完成一轮探测。
- **适用场景**：对确认的 Web 端点补充隐藏参数，扩大攻击面。
- **局限**：发现的参数是**线索**，需结合业务复核；主动发包，需授权。
- **接入状态**：未安装；无调度。

## 2. 安装方式（官方 README，待核对）

- `pip3 install arjun`；或克隆后 `python3 setup.py install`。
- 建议独立 venv（与 wafw00f 一致），纳入 `tools/tool-lock.json`（**安装事项，不在本批**）。

## 3. 输入准备与场景命令（官方 README，待核对）

- **输入**：单个 URL；支持从 BurpSuite 导出、文本文件、raw HTTP 请求文件导入多目标。
- **输出**：可导出 BurpSuite、纯文本或 JSON 文件。
- **能力**：支持 `GET/POST/POST-JSON/POST-XML`；自动处理速率限制与超时；可从 JS 或 3 个外部来源被动提取参数；支持自定义 HTTP headers（见官方 Wiki）。
- **具体 flag 名**：记载于官方 Wiki Usage 页（本次未抓取），**以 `arjun --help` 为准**。

```bash
# 示例（官方 README 形态，未本机验证；安装后核对）
arjun -u "$URL" -oJ "$OUT/arjun.json"
```

## 4. 输出与解析（待核对）

- JSON/文本导出；按端点组织发现的参数。解析方式待核对。

## 5. 结果衔接与入库（规划）

- 衔接：gau/waybackurls/katana 发现的端点 → arjun 参数发现 → 人工复核 →（必要时）ffuf/nuclei。
- 入库：不自动入库。

## 6. 去重与复核（规划）

- 去重键：`(endpoint, param)`；发现的参数不盲目用于构造请求，先评估语义。

## 7. 常见失败（预期，待核对）

| 情况 | 处理 |
|---|---|
| 请求被限流 | 工具自动处理速率；必要时降速 |
| 参数误报 | 人工结合业务复核 |
| 用法差异 | 以安装后 `--help` 为准 |

## 8. 官方来源与核对记录

- 官方文档核对：[PyPI arjun](https://pypi.org/pypi/arjun/json)（README 全文+版本史）、[GitHub 仓库](https://github.com/s0md3v/Arjun)、[官方 Wiki Usage](https://github.com/s0md3v/Arjun/wiki/Usage)（未抓取）。
- 与 x8 的差异见 [x8.md](x8.md)。
- 待验证：安装、flag 细节、字典规模、被动来源、与现有链路的衔接。

# wafw00f（WAF 指纹识别）

> 状态：**仅安装，未自动调度**
> 版本：2.4.2（固定）
> 位置：WSL `~/asm-ws/tools/wafw00f/.venv/bin/wafw00f`（独立 venv）
> 核对日期：2026-10-10（本机帮助核对：`data/validation/tool-help/wafw00f.txt`）
> 证据：本机 `wafw00f --help`

## 1. 用途、场景与局限

- **用途**：识别目标站点前置的 WAF（Web 应用防火墙）指纹。
- **适用场景**：解释 `403/502` 等异常状态、过滤行为是否可能来自 WAF。
- **局限**：WAF 指纹是**辅助线索**，不证明漏洞、组织归属或 CDN 源站 IP；**没检测到不代表无 WAF**（可能只是没命中指纹库）。**`-r` 在本工具表示“不跟随重定向”**，与 ffuf 的 `-r`（跟随）含义相反——不同工具参数不能只按同名字母套用。
- **接入状态**：已安装、未自动调度；原生 JSON 不自动入库。

## 2. 实际接入状态

无自动调度。独立 venv 安装，PATH 需含 `~/asm-ws/tools/wafw00f/.venv/bin`（索引的通用 export 已含）。

## 3. 输入准备与场景命令

> 前置：WSL、venv 在 PATH；`$URL` 为批准目标。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 单目标：不跟随重定向，输出 JSON
run_logged wafw00f wafw00f -r -o "$OUT/wafw00f.json" "$URL"
# 批量输入、明确输出类型、慢网络超时
run_logged wafw00f-batch wafw00f -r -i "$OUT/urls.txt" -f json -T 20 -o "$OUT/wafw00f-batch.json"
# 只列出可检测的 WAF 指纹
run_logged wafw00f-list wafw00f --list
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 单目标 | WSL | 批准 URL | `-r` 不跟随跳转、`-o` 输出（按扩展名定格式） | `$OUT/wafw00f.json` | 指纹记录 | rc≠0；网络/TLS 错误 |
| 批量 | WSL | urls.txt | `-i`、`-f json`、`-T` 超时 | `$OUT/wafw00f-batch.json` | 每 URL 记录 | 超时增多→增大 `-T` |
| `--list` | 任意 | — | — | stdout 文本 | 指纹清单 | — |

**参数含义**（本机 2.4.2）：`-r/--noredirect` 不跟随 3xx；`-o` 输出（按扩展名 csv/json/text，`-` 为 stdout）；`-f` 强制格式；`-i` 输入文件（text 每行一个；csv/json 需 `url` 列/字段）；`-T` 超时秒；`-a/--findall` 找所有匹配（默认命中第一个即停）；`-p` 代理。

## 4. 原生输出格式与解析

JSON（`-o *.json` 或 `-f json`）是数组，元素含 `url`、`detected`、`firewall`、`manufacturer` 等。脱敏样例：

```json
[{"url":"https://authorized.invalid","detected":true,"firewall":"Cloudflare (Cloudflare Inc.)","manufacturer":"Cloudflare Inc."}]
```

**解析方法**：`json.load` 读数组；`detected=false` 时 `firewall` 为 `None`/通用值，表示**未命中**而非“无 WAF”。`--list` 输出纯文本指纹名清单。

## 5. 结果衔接与入库

- 衔接：WAF 指纹用于解释 httpx/ffuf 的 403/502、过滤行为；辅助判断 CDN/WAF 前置。
- 入库：**不自动入库**；作为人工分析线索。

## 6. 去重、来源与复核

- 去重键：URL。
- 来源保留：JSON 与 argv/rc 留存。
- 时间戳：保存 `started-utc.txt` 与 rc。
- 独立复核：对同一目标用不同工具（httpx `-cdn`、响应头 server/via）交叉；与 Stage 5 CDN 指纹对照。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 没检测到 WAF | 可能没命中指纹，不能断言无 WAF |
| 重定向页面无结果 | 保留原状态/Location，再核对目标范围（`-r` 表示不跟随，跳转目标需另行评估） |
| TLS/连接异常 | 查 stdout/stderr、网络与 DNS；不改变候选置信度 |
| 批量超时 | 增大 `-T`；核对目标可达性 |
| 版本参数差异 | 以本机 `wafw00f --help`（2.4.2）为准 |

## 8. 官方来源与核对记录

- 官方仓库核对：[EnableSecurity/wafw00f](https://github.com/EnableSecurity/wafw00f)；选项以本机 `--help` 为准。
- 本机证据：`wafw00f --help` 原文 `data/validation/tool-help/wafw00f.txt`。
- 待验证：指纹库版本与实际命中率；与 httpx/Stage 5 CDN 指纹的一致性。

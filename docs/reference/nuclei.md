# nuclei（模板化漏洞/暴露检测）

> 状态：**仅安装（二进制）**；模板集**未单独验收**，主流水线**不自动运行**漏洞模板
> 版本：3.11.1（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/nuclei`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/nuclei.txt`、`tool-help/nuclei.txt`）
> 证据：本机 `nuclei -h`

## 1. 用途、场景与局限

- **用途**：基于模板对目标做漏洞/暴露/错误配置探测。
- **适用场景**：对**已选定并审阅过**的模板，在授权范围内做定点验证。
- **局限**：安装二进制**不代表**模板集完整或规则已验收；**模板命中是待复核线索，不自动标成已确认漏洞**（可能来自统一返回页、过滤页或版本猜测）。不要把默认全模板集当成“已完成暴露面核验”。请求行为取决于模板本身——运行前必须阅读模板的实际请求与匹配条件。
- **接入状态**：已安装、未接入；原生 JSONL 不自动入库。

## 2. 实际接入状态

无自动调度。本项目当前不自动执行模板。模板文件需自行准备（`-t` 路径是占位符），并先 `-validate` 校验。`-dr` 关闭 HTTP 模板跳转、`-ni` 排除 OAST 外带交互——这是本项目的默认收敛要求，但具体请求仍以模板为准。

## 3. 输入准备与场景命令

> 前置：WSL；`$URL` 为批准目标；`$TEMPLATE` 为已审阅模板路径（占位符，需自行准备）。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 模板文件须先准备，路径是占位符
TEMPLATE='/path/to/approved-template.yaml'
# 校验模板语法/签名/依赖
run_logged nuclei-validate nuclei -t "$TEMPLATE" -validate -duc
# 定点运行：关跳转、排除 OAST、限速、JSONL
run_logged nuclei nuclei -u "$URL" -t "$TEMPLATE" -dr -ni -duc -rl 10 -jsonl -o "$OUT/nuclei.jsonl"
# 批量批准 URL，降低并发
run_logged nuclei-batch nuclei -l "$OUT/urls.txt" -t "$TEMPLATE" -dr -ni -duc -rl 5 -c 2 -jsonl -o "$OUT/nuclei-batch.jsonl"
run_logged nuclei-help nuclei -h
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| `-validate` | WSL | 已备模板 | `-t`、`-validate`、`-duc` | stdout | 模板校验通过 | 语法/签名错误 |
| 定点运行 | WSL | 批准 URL+模板 | `-u`、`-t`、`-dr`、`-ni`、`-rl`、`-jsonl` | `$OUT/nuclei.jsonl` | 命中行 | rc≠0；模板未加载 |
| 批量 | WSL | urls.txt | `-l`、`-c` 并发 | `$OUT/nuclei-batch.jsonl` | 每命中一条 | 速率过高→降 `-rl`/`-c` |
| `-h` | 任意 | — | — | stdout 文本 | 打印帮助 | — |

**参数含义**（本机 3.11.1）：`-u/-l` 目标/列表、`-t` 模板、`-validate` 只校验、`-dr` 关 HTTP 跳转、`-ni` 排除 OAST、`-rl` 每秒请求、`-c` 并发、`-jsonl` JSONL 输出、`-duc` 关更新检查。

## 4. 原生输出格式与解析

JSONL 逐行一个命中对象，常见字段：`template-id`、`info`（name/severity）、`host`、`matched-at`、`type`、`matcher-status`、`request`/`response`（除非 `-or` 省略）。脱敏样例：

```json
{"template-id":"exposed-env","info":{"name":"Exposed .env","severity":"medium"},"host":"https://authorized.invalid","matched-at":"https://authorized.invalid/.env","type":"http"}
```

**解析方法**：逐行 `json.loads`；按 `template-id`+`matched-at` 复查；**命中需人工对照原始请求/响应与匹配条件**，只归档必要证据并脱敏。

## 5. 结果衔接与入库

- 衔接：确认后的命中 → review/人工判定 → 必要时进入 findings。
- 入库：**不自动入库**；命中不自动成为漏洞。
- 与 ffuf 的统一返回页基线、httpx 的状态/长度联合复核，排除误报。

## 6. 去重、来源与复核

- 去重键：`(template-id, matched-at, 证据)`；同键合并。
- 来源保留：JSONL + 模板路径 + argv/rc。
- 时间戳：保存 `started-utc.txt` 与 rc。
- 独立复核：对不存在路径/已知安全路径做对照，确认匹配不是统一返回页；必要时 `-ms` 显示匹配失败状态辅助定位。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 模板不存在 | 核对显式 `-t`；安装二进制不保证模板文件存在 |
| validate 失败 | 看语法/签名/依赖；按固定版本修复 |
| 命中很多相同结果 | 对照不存在路径、状态与原始匹配条件；疑统一返回页 |
| 结果为空 | 检查模板加载数量、适用协议、错误/超时；不断言“无问题” |
| OAST 干扰 | 已用 `-ni` 排除；确认模板无自带外带请求 |
| 版本参数差异 | 以本机 `nuclei -h`（3.11.1）为准 |

## 8. 官方来源与核对记录

- 官方仓库核对：[projectdiscovery/nuclei](https://github.com/projectdiscovery/nuclei) 与模板库 [nuclei-templates](https://github.com/projectdiscovery/nuclei-templates)；版本 3.11.1 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`nuclei -h` 原文 `data/validation/reference-help/nuclei.txt` 与 `data/validation/tool-help/nuclei.txt`。
- 待验证：模板集的版本固定与验收；命中判定的误报基线；是否/如何以受控方式纳入 review 流程。

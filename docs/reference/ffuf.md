# ffuf（Web 路径/内容爆破）

> 状态：**仅安装，未接入 Stage 7**
> 版本：2.3.0（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/ffuf`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/ffuf.txt`、`web-tool-help/ffuf.txt`）
> 证据：本机 `ffuf -h`

## 1. 用途、场景与局限

- **用途**：用字典对目标做路径/参数/虚拟主机等模糊测试，发现隐藏端点。
- **适用场景**：对批准的 Web 目标做目录/文件爆破、统一返回页（catch-all）识别后的差异筛选。
- **局限**：**输入字典是候选集合，不是资产事实**；命中需排除统一返回页（catch-all）再人工复核。**默认不跟随重定向**（`-r` 需显式开）。`-ac` 自动校准不能代替原始记录与人工判断；过滤条件过宽会漏真实页面。`502` 单独只作候选（项目记为 `backend_filtered_candidate`）。
- **接入状态**：已安装、未接入 Stage 7；原生 JSON 不自动入库。框架 Stage 7 路径探测用 Windows httpx 库（速率由 `rates.ffuf_tps` 控制），与这里的二进制是两回事。

## 2. 实际接入状态

无自动调度。字典来自 SecLists 稀疏检出（见 [seclists.md](seclists.md)），默认字典是 `raft-medium-directories.txt`。运行前确认字典文件实际存在。

## 3. 输入准备与场景命令

> 前置：WSL；目标 URL 为批准主机；字典文件存在（`$WORDLIST` 见 [索引](README.md)）。**`$URL/FUZZ` 的 FUZZ 是注入点占位**。

```bash
# 初步：保留所有状态，避免 403/502 被默认匹配规则忽略
run_logged ffuf ffuf -u "$URL/FUZZ" -w "$WORDLIST" -mc all -rate 50 -t 5 -noninteractive -of json -o "$OUT/ffuf.json"
# 有统一返回页时另跑自动校准，原始结果仍保留
run_logged ffuf-calibrated ffuf -u "$URL/FUZZ" -w "$WORDLIST" -ac -mc all -rate 10 -t 2 -noninteractive -of json -o "$OUT/ffuf-calibrated.json"
# 明确测得统一返回长度后再过滤；1234 仅是占位测量值，需先实测
run_logged ffuf-size ffuf -u "$URL/FUZZ" -w "$WORDLIST" -mc all -fs 1234 -rate 10 -noninteractive -of json -o "$OUT/ffuf-size.json"
# 原生多格式结果留作人工阅读
run_logged ffuf-formats ffuf -u "$URL/FUZZ" -w "$WORDLIST" -rate 10 -noninteractive -of all -o "$OUT/ffuf-formats"
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 初步全状态 | WSL | 批准 URL+字典 | `-u …/FUZZ`、`-w`、`-mc all`、`-rate`、`-t`、`-of json` | `$OUT/ffuf.json` | 各状态命中记录 | 几乎全命中→疑统一返回页 |
| 自动校准 | WSL | 同上 | `-ac` | `$OUT/ffuf-calibrated.json` | 过滤后候选 | `-ac` 误过滤→用原始结果复核 |
| 按长度过滤 | WSL | 已测 catch-all 长度 | `-fs <len>` | `$OUT/ffuf-size.json` | 排除统一长度 | 误删真实页面→对照原始 |
| 多格式 | WSL | 同上 | `-of all` | `$OUT/ffuf-formats.*` | json/csv/html/md | — |

**参数含义**（本机 2.3.0）：`-mc` 匹配状态码（默认 `200-299,301,302,307,401,403,405,500`，`all` 全保留）、`-fs/-fc/-fl/-fw` 按长度/状态/行/词过滤、`-rate` 每秒请求（默认 0 不限）、`-t` 线程（默认 40）、`-timeout` 秒（默认 10）、`-ac` 自动校准、`-noninteractive` 关交互、`-of` 输出格式。**不开 `-r`** 保持不跟随跳转。

## 4. 原生输出格式与解析

JSON（`-of json`）顶层含 `results` 数组，每项：`input.FUZZ`、`url`、`status`、`length`、`words`、`lines`、`content_type`、`redirectlocation`。脱敏样例：

```json
{"results":[{"input":{"FUZZ":"admin"},"url":"https://authorized.invalid/admin","status":301,"length":169,"words":5,"lines":8,"content_type":"text/html","redirectlocation":"/admin/"}]}
```

**解析方法**：`json.load` 取 `results`；逐条结合**三个不存在路径基线**（状态/长度/哈希）判断是否为统一返回页。`-ac` 或 `-fs` 过滤的结果必须与未过滤原始结果对照。`-of all` 同时生成 csv/ejson/html/md/ecsv。

## 5. 结果衔接与入库

- 衔接：确认的真实路径 → katana 爬取 / httpx 复核 / nuclei 模板目标。
- 入库：**当前不自动入库**；接入需补“统一返回页基线 + 状态复核 + 范围过滤”适配器。
- 命中条目是**候选**；结合 Stage 7 的 catch-all 判定（`catch_all:` facts）与 `differential()` 逻辑人工确认。

## 6. 去重、来源与复核

- 去重键：完整 URL（含路径与查询）；同一 URL 不同状态分别保留。
- 来源保留：JSON `results` + argv/rc；`-of all` 留多格式。
- 时间戳：保存 `started-utc.txt` 与 rc。
- 独立复核：用三个随机不存在路径求基线（状态、长度、sha256），与命中条目的签名对比；`words/lines/length` 三签名一致多半是统一返回页。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 几乎每条都命中 | 统一返回页；保存未过滤与校准两份结果，人工对比 |
| 超时/服务负载增加 | 降 `-rate`/`-t`，调 `-timeout`，查 stderr |
| 字典不存在 | SecLists 为稀疏检出；先核对实际文件路径 |
| 502 被当泄露 | 502 只是候选（backend_filtered_candidate）；需基线+归属确认 |
| 误过滤真实页面 | `-fs/-ac` 过宽；回到 `-mc all` 原始结果复核 |
| JSON 没进总表 | 原生 ffuf 无自动导入适配器，属预期 |
| 版本参数差异 | 以本机 `ffuf -h`（2.3.0）为准 |

## 8. 官方来源与核对记录

- 官方仓库核对：[ffuf/ffuf](https://github.com/ffuf/ffuf)；版本 2.3.0 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`ffuf -h` 原文 `data/validation/reference-help/ffuf.txt` 与 `data/validation/web-tool-help/ffuf.txt`；框架基线逻辑 [s7_web.py](../../asm/stages/s7_web.py)（`catch_all`、`differential`）。
- 待验证：接入 Stage 7 的统一返回页基线适配器；真实目标的过滤阈值标定。

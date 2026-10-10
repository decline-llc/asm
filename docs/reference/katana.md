# katana（Web 爬虫）

> 状态：**仅安装，未接入 Stage 7**
> 版本：1.8.0（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/katana`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/katana.txt`、`web-tool-help/katana.txt`）
> 证据：本机 `katana -h`

## 1. 用途、场景与局限

- **用途**：爬取目标站点的 URL、JS 端点、表单等线索。
- **适用场景**：对批准的 Web 目标做链接/端点发现；配合精确 scope 做有界爬取。
- **局限**：**默认 `-fs rdn`**（按注册域判定范围）且**默认跟随重定向**——这两者都不能直接当作项目边界；接入必须显式 `-cs`（精确 crawl-scope 正则）、`-dr`（关跳转）、`-duc`。普通爬取**不等于浏览器执行**（动态页面需 headless，但 headless 的每请求范围控制尚待实现）。`-kb-validate-secrets` 会向提供商发验证请求，**禁止启用**。
- **接入状态**：已安装、未接入 Stage 7；未来自动接入须先用回环夹具证明“越界请求零到达”。原生 JSONL 不自动入库。

## 2. 实际接入状态

无自动调度。`-cs` 正则必须与目标 URL 同步改成**精确批准主机**，不能保留占位正则。`-dr` 是显式关闭跳转（官方默认跟随）。`-or`/`-ob` 用于减少原始请求/响应正文的存储，需要正文证据时另行选择并脱敏。

## 3. 输入准备与场景命令

> 前置：WSL；`$URL` 与 `SCOPE` 都改为批准主机。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# scope 的占位主机需与 URL 一起改为批准主机
SCOPE='^https://authorized\.invalid(?::443)?(?:/|$)'
# 有界爬取：精确 scope + 关跳转 + 关更新 + 限速 + JSONL
run_logged katana katana -u "$URL" -cs "$SCOPE" -dr -duc -d 2 -rl 10 -j -or -ob -o "$OUT/katana.jsonl"
# JS 端点线索，仍保持同一精确范围
run_logged katana-js katana -u "$URL" -cs "$SCOPE" -dr -duc -jc -d 3 -rl 5 -j -or -ob -o "$OUT/katana-js.jsonl"
# robots/sitemap 已知文件，深度至少 3
run_logged katana-known katana -u "$URL" -cs "$SCOPE" -dr -duc -kf all -d 3 -rl 5 -j -or -ob -o "$OUT/katana-known.jsonl"
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| 有界爬取 | WSL | 批准 URL+精确 SCOPE | `-u`、`-cs`、`-dr`、`-duc`、`-d` 深度、`-rl`、`-j`、`-or`、`-ob` | `$OUT/katana.jsonl` | 范围内 URL | 范围外记录→核 `-cs`/`-fs` |
| JS 端点 | WSL | 同上 | `-jc` JS 解析 | `$OUT/katana-js.jsonl` | JS 提取的端点 | 动态渲染缺失→非 headless 限制 |
| 已知文件 | WSL | 同上 | `-kf all`、`-d≥3` | `$OUT/katana-known.jsonl` | robots/sitemap 路径 | 深度不足→漏抓 |

**参数含义**（本机 1.8.0）：`-d` 爬取深度（默认 3）、`-rl` 每秒请求（默认 150）、`-c` 并发（默认 10）、`-timeout` 秒（默认 10）、`-cs` 范围正则、`-fs` 预定义范围域（默认 `rdn`）、`-dr` 关跳转、`-jc` JS 解析、`-kf` 已知文件、`-j` JSONL、`-or`/`-ob` 省略原始请求/响应体。

## 4. 原生输出格式与解析

JSONL 逐行对象，关键字段：`request.endpoint`（或顶层 `url`，随字段选择）、`response.status_code`、`-jc` 时的 JS 端点、`-fx` 时的表单元素。脱敏样例：

```json
{"timestamp":"2026-10-10T00:00:00Z","request":{"method":"GET","endpoint":"https://authorized.invalid/app.js"},"response":{"status_code":200}}
```

**解析方法**：逐行 `json.loads`；先做**范围过滤**再按完整 URL 保留。查询参数排序等语义去重需另行处理（当前不盲目删参）。JS 中出现的链接不表示已存在服务。

## 5. 结果衔接与入库

- 衔接：范围内 URL/端点 → httpx 存活复核 → ffuf 路径补充 → （必要时）gowitness 截图。
- 入库：**当前不自动入库**；接入需证明范围控制有效。
- 越界 URL 一律丢弃；`-do`（显示范围外）仅用于核对 scope 是否过宽，不作为采集结果。

## 6. 去重、来源与复核

- 去重键：完整 URL；同 URL 不同 query 参数保留（可能影响语义）。
- 来源保留：JSONL + argv/rc；`-sfd` 可按主机存字段。
- 时间戳：JSONL 自带 `timestamp`；保存 `started-utc.txt`。
- 独立复核：用回环夹具统计“请求是否越界”；对照 `-cs` 正则的主机边界与默认 `-fs rdn` 的差异。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 跳转后没继续 | `-dr` 是显式关闭；人工核对 Location 范围 |
| 范围看起来太大 | 检查 `-cs` 正则主机边界与默认 `-fs rdn` |
| 动态页面少结果 | 普通爬取不等于浏览器执行；headless 需请求范围控制 |
| 发现凭据样文本 | 不启用 `-kb-validate-secrets`（会发外部验证请求） |
| 速率被限 | 降 `-rl`/`-c`、加 `-rd` 延迟 |
| 版本参数差异 | 以本机 `katana -h`（1.8.0）为准 |

## 8. 官方来源与核对记录

- 官方仓库核对：[projectdiscovery/katana](https://github.com/projectdiscovery/katana)；版本 1.8.0 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`katana -h` 原文 `data/validation/reference-help/katana.txt` 与 `data/validation/web-tool-help/katana.txt`。
- 待验证：接入前的“越界请求零到达”回环证明；headless 模式的每请求范围控制；与 Stage 7 Windows httpx 的结果对照。

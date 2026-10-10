# SecLists（字典）

> 状态：**仅安装（字典输入，非采集工具）**
> 版本：2026.1，固定 commit `190c6f7bd58c847ceadfe57d9853592737f059e8`（见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/wordlists/SecLists`（Git sparse 检出）
> 核对日期：2026-10-10（版本锁与部署说明核对）
> 证据：[tool-lock.json](../../tools/tool-lock.json)、[tools/README.md](../../tools/README.md)

## 1. 用途、场景与局限

- **用途**：为爆破类工具提供候选字典（DNS 子域、Web 路径/文件/扩展名）。
- **适用场景**：ffuf 的 `-w` 字典、subfinder/其它工具的爆破输入（需主动授权时）。
- **局限**：**字典是工具输入，不是已发现资产**；当前为**稀疏检出 7 个文件**（README、LICENSE、`Discovery/DNS/subdomains-top1million-5000.txt`、`Discovery/Web-Content/raft-medium-{directories,extensions,files,words}.txt`），完整集约 1.96GB、按需选择。Stage 4 当前用内置 `DNS_PREFIXES`，**不自动读全部 SecLists**；ffuf 由 `-w` 显式选文件。
- **接入状态**：作为输入被引用；不产出结果、不入库。

## 2. 实际接入状态

不调度。被 ffuf 等以 `-w <path>` 引用。完整检出入口见 [RUNBOOK](../RUNBOOK.md) 的 `ASM_SECLISTS_FULL=1`。

## 3. 输入准备与场景命令（核对与扩展）

> 前置：WSL；目录已是固定 commit 的 sparse 检出。通用变量见 [索引](README.md)。

```bash
# 核对版本与检出清单
git -C "$HOME/asm-ws/wordlists/SecLists" rev-parse HEAD
git -C "$HOME/asm-ws/wordlists/SecLists" sparse-checkout list
# 核对所需字典存在与规模
wc -l "$HOME/asm-ws/wordlists/SecLists/Discovery/DNS/subdomains-top1million-5000.txt"
wc -l "$HOME/asm-ws/wordlists/SecLists/Discovery/Web-Content/raft-medium-directories.txt"
# 需要另一份字典时扩展选择（不切换版本）
git -C "$HOME/asm-ws/wordlists/SecLists" sparse-checkout add --no-cone Discovery/Web-Content/common.txt
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| `rev-parse HEAD` | WSL | 检出存在 | — | commit SHA | 与 tool-lock 一致 | 不一致→被改动 |
| `sparse-checkout list` | WSL | 同上 | — | 路径清单 | 含所需字典 | 缺失→扩展或重装 |
| `wc -l` | WSL | 文件存在 | — | 行数 | 规模符合预期 | 文件缺失 |
| `sparse-checkout add` | WSL | 网络可用 | `--no-cone` | 新增文件 | 取回字典 | lazy-fetch 超时→查网络/代理 |

**注意**：扩展可能触发网络 lazy-fetch；先保留本地改动，再核对版本/文件哈希，不直接覆盖字典内容。完整安装所需空间与下载显著增加，按实际需要选择。

## 4. 输出格式与解析

- 纯文本字典，每行一个候选（路径/子域前缀/扩展名等）。无结构化输出。
- 被引用时按工具要求读入（ffuf `-w` 逐行替换 FUZZ）。

## 5. 结果衔接与入库

- 衔接：字典 → ffuf 爆破 / （主动授权时）DNS 字典枚举。
- 入库：不直接入库；字典命中经工具产出后再按该工具的规则处理。

## 6. 去重、来源与复核

- 去重：字典内部一般已去重；多字典合并时自行去重，不把同名结果与输入字典互相覆盖。
- 来源保留：以固定 commit + sparse 清单为准；记录所用字典路径。
- 时间戳：commit 即版本时间；采集时间由使用它的工具记录。
- 独立复核：`rev-parse HEAD` 对照 tool-lock；`wc -l` 核对规模；哈希对照（部署时已按 Git tree blob SHA 校验）。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 文件找不到 | 看 `sparse-checkout list`，核对大小写/路径；必要时扩展检出 |
| 字典太大/运行太久 | 选当前阶段需要的类型与规模，控制工具速率 |
| Git 请求超时 | 保留已校验的文件/元数据，查 WSL HTTPS/代理路径 |
| 版本被改动 | `rev-parse HEAD` 不符 tool-lock 时停止并核对 |

## 8. 官方来源与核对记录

- 官方仓库核对：[danielmiessler/SecLists](https://github.com/danielmiessler/SecLists)；版本锁 2026.1/commit `190c6f7b` 与 [tool-lock.json](../../tools/tool-lock.json) 一致。
- 本机证据：稀疏检出清单与部署说明 [tools/README.md](../../tools/README.md)；安装验收见 ACCEPTANCE（SecLists 为稀疏检出）。
- 待验证：是否扩展其它所需字典；完整检出的空间/下载成本评估。

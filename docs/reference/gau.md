# gau（getallurls，调研笔记，未安装）

> 状态：**尚未安装** — 本页为调研笔记，所有命令与参数**待安装后核对**（`gau --help`）
> 版本（官方，调研时）：最新 tag **v2.2.4**（2024-10-28，来源 [pkg.go.dev](https://pkg.go.dev/github.com/lc/gau/v2)）
> 预计位置：WSL `~/asm-ws/bin/gau`（未安装）
> 核对日期：2026-10-10（官方 README 经 pkg.go.dev 渲染核对，**非本机验证**）
> 证据：[pkg.go.dev/github.com/lc/gau/v2](https://pkg.go.dev/github.com/lc/gau/v2)、[GitHub 仓库](https://github.com/lc/gau)

> ⚠️ 本文内容来自官方 README 的**调研**，**未在本机验证**；安装后以实际版本 `gau --help` 重写。

## 1. 用途、场景与局限

- **用途**：从 AlienVault OTX、Wayback Machine、Common Crawl、URLScan 四个来源抓取指定域名的**已知 URL**。
- **适用场景**：补充历史/公开 URL 线索（补 katana/爬虫覆盖不到的旧端点）。
- **局限**：输出是**历史/已知 URL**，不代表当前存活；需交 httpx 复核。Docker 方式不支持 stdin 管道。
- **接入状态**：未安装；无调度。

## 2. 安装方式（官方 README，待核对）

- 源码：`go install github.com/lc/gau/v2/cmd/gau@latest`
- 克隆构建：`git clone https://github.com/lc/gau.git && cd gau/cmd && go build`
- release 二进制（如 `gau_2.0.6_linux_amd64.tar.gz`）
- Docker：`docker run --rm sxcurity/gau:latest --help`（不支持 stdin）

## 3. 输入准备与场景命令（官方 README，待核对）

- **输入**：stdin（`printf example.com | gau`、`cat domains.txt | gau`）或位置参数（`gau example.com google.com`）。
- **输出**：默认 stdout 行文本 URL；`--o <file>` 写文件；`--json` 输出 JSON。
- **关键参数**：`--providers`（wayback,commoncrawl,otx,urlscan）、`--threads`、`--timeout`（秒）、`--retries`、`--proxy`（http://或socks5://）、`--blacklist`（排除扩展名）、`--mc`/`--fc`（匹配/过滤状态码）、`--mt`/`--ft`（匹配/过滤 MIME）、`--fp`（同端点参数去重）、`--subs`（含子域）、`--from`/`--to`（YYYYMM）、`--config`（默认 `$HOME/.gau.toml`）、`--verbose`。

```bash
# 示例（官方 README 形态，未本机验证；安装后核对）
printf '%s\n' "$ROOT" | gau --threads 5 --timeout 30 --o "$OUT/gau.txt"
# JSON 输出便于解析
printf '%s\n' "$ROOT" | gau --json --o "$OUT/gau.json"
```

## 4. 输出格式与解析（待核对）

- 文本：每行一个 URL。JSON：结构化记录。
- 解析：文本按行；JSON 逐条。先做范围过滤（host 在 root 内），再按完整 URL 保留（不盲目删查询参数）。

## 5. 结果衔接与入库（规划）

- 衔接：gau URL → 范围过滤 → httpx 存活复核 → katana/报告。
- 入库：不自动入库；历史 URL 经 httpx 复核确认存活后才作线索。

## 6. 去重与复核（规划）

- 去重键：完整 URL；`--fp` 控制同端点不同参数的去重。
- 来源保留：标记来源（gau/wayback/otx…）；记录采集时间。
- 独立复核：与 waybackurls、katana 结果对照；httpx 复核存活。

## 7. 常见失败（预期，待核对）

| 情况 | 处理 |
|---|---|
| 输出大量历史死链 | 交 httpx 复核存活，不当现状 |
| 来源限流 | 降 `--threads`、加 `--timeout`/`--retries` |
| 参数去重误删语义 | 不用 `--fp` 或人工核对 |

## 8. 官方来源与核对记录

- 官方文档核对：[pkg.go.dev/github.com/lc/gau/v2](https://pkg.go.dev/github.com/lc/gau/v2)（README 全文+版本）、[GitHub releases](https://github.com/lc/gau/releases)（未直取）。
- 待验证：安装、参数细节、各 provider 可用性、与 httpx 的衔接。

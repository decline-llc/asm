# Amass（调研笔记，未安装）

> 状态：**尚未安装** — 本页为调研笔记，所有命令与参数**待安装后核对**（`amass --help`）
> 版本（官方，调研时）：v5 大版本，模块 `github.com/owasp-amass/amass/v5`，最新 tag **v5.1.1**（来源 [pkg.go.dev](https://pkg.go.dev/github.com/owasp-amass/amass/v5)）
> 预计位置：WSL `~/asm-ws/bin/amass`（未安装）
> 核对日期：2026-10-10（官方文档核对，**非本机验证**）
> 证据：[官方文档站](https://owasp-amass.github.io/docs/)、[pkg.go.dev](https://pkg.go.dev/github.com/owasp-amass/amass/v5)

> ⚠️ 本文全部内容来自官方文档/仓库的**调研**，**未在本机验证**；安装后需以实际版本 `amass --help` 重写本页命令与输出。

## 1. 用途、场景与局限

- **用途**（官方定位）：OWASP 攻击面测绘框架，通过 OSINT 收集与主动侦察做网络测绘与外部资产发现；远超基础子域枚举，核心模型是 Open Asset Model（OAM）。
- **适用场景**：比 subfinder 更深的外部资产发现与关系建模；多数据源聚合。
- **局限**：功能强大但更重；v5 输出进入 **Asset Database**（PostgreSQL 或内嵌 Triples 存储），不是简单行文本——接入需要设计“资产库 → 本框架”的映射。主动侦察（`-active`）属于主动行为，需授权。
- **接入状态**：未安装；无调度。

## 2. 安装方式（官方文档，待核对）

- 源码：`CGO_ENABLED=0 go install -v github.com/owasp-amass/amass/v5/cmd/amass@main`（街道地址解析可选 `CGO_ENABLED=1` 编译 libpostal）。
- Homebrew：`brew tap owasp-amass/homebrew-amass && brew install amass`。
- Docker：`docker pull owaspamass/amass:latest`；Compose 见官方 amass-docker-compose（含 PostgreSQL）。

> 本项目 WSL 用独立 venv/二进制管理；建议优先评估 release 二进制或 `go install` 固定版本，并纳入 `tools/tool-lock.json`（**安装事项，不在本批范围**）。

## 3. 输入准备与场景命令（官方文档，待核对）

- v5 官方文档仍用**子命令**结构：`amass enum -d <domain>`；配套 `oam_subs`、`oam_track`、`oam_viz`、`oam_assoc`、`amass_engine` 等。
- 输入：`-d <域名>`；`-active` 开启主动侦察；配置 `config.yaml`（含 database 连接串）与 `datasources.yaml`（数据源凭据）。
- **关键参数**：官方文档明确出现的只有 `-d`、`-active`；并发/超时/限速/数据源开关等**以安装版本 `amass --help` 为准**（CLI 参考文档尚未完善，[待安装后核对]）。

```bash
# 示例（官方文档形态，未本机验证；安装后核对）
amass enum -d "$ROOT"
# 主动侦察（需授权）
# amass enum -active -d "$ROOT"
```

## 4. 输出与解析（待核对）

- 资产数据写入 Asset Database（OAM 模型：资产/关系/属性）；stdout 细节[待安装后核对]。
- 解析：需从资产库导出或查询，再映射到本框架 `domains`/`assets`。

## 5. 结果衔接与入库（规划）

- 衔接：Amass 资产库 → 导出子域/关系 → Stage 5 解析。
- 入库：需新增适配器；当前不安装、不调度、不入库。

## 6. 去重与复核（规划）

- 域名标准化同索引总则；多来源保留；OAM 关系可作补充证据。

## 7. 常见失败（预期，待核对）

| 情况 | 处理 |
|---|---|
| 版本命令结构差异 | v3/v4/v5 结构不同；以安装版本 `--help` 为准 |
| 输出进数据库而非文本 | 需读 OAM 存储或导出，不能按行解析 |
| 主动侦察越界 | `-active` 属主动；确认授权与范围 |

## 8. 官方来源与核对记录

- 官方文档核对：[owasp-amass.github.io/docs](https://owasp-amass.github.io/docs/)、[pkg.go.dev/.../v5](https://pkg.go.dev/github.com/owasp-amass/amass/v5)。
- 版本差异说明：v3 用 `amass enum/intel` 子命令，v5 保留子命令但重构为 OAM 资产库；v3→v4→v5 的具体发行说明差异**未能从官方渠道完整核验**（GitHub releases 抓取受限），**以安装版本 `--help` 与官方 release 为准**。
- 待验证：安装、命令结构、输出存储、数据源配置、与本框架的映射。

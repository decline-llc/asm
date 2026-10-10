# subfinder（被动子域枚举）

> 状态：**已自动调用**（Stage 4）
> 版本：2.17.0（固定，见 [tool-lock.json](../../tools/tool-lock.json)）
> 位置：WSL `~/asm-ws/bin/subfinder`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/subfinder.txt`）
> 证据：本机 `subfinder -h`、调度代码 [s4_subdomain.py](../../asm/stages/s4_subdomain.py)

## 1. 用途、场景与局限

- **用途**：从被动在线来源（证书透明、公开数据集、情报源等）枚举目标 root 下的子域名。
- **适用场景**：Stage 4 每个范围内 root 的被动子域收集；也适合人工对单个/批量批准 root 做来源核对。
- **局限**：纯被动，**不主动探测目标**；结果覆盖面取决于来源与是否配置各提供商 API key（`provider-config.yaml`）。它只产出域名，**不做解析**——解析归 Stage 5（dnsx/dig）。`-all` 不是默认，未配 key 的来源会被跳过或限流；`-recursive` 是选择“支持递归的来源”，不代表对任意子域做主动爆破。
- **接入状态**：主流程 Stage 4 自动调用（`subfinder -d <root> -silent -duc -o {job}/subdomains.txt`），幂等缓存；人工原生调用结果**不自动入库**。

## 2. 实际接入状态与凭据

- 主流程只取 `-silent` 文本输出（每行一个子域），经 `accept()` 做 root/SaaS 范围过滤与标准化后入库 `domains`，来源标 `subfinder`。
- **凭据位置**：subfinder 的提供商 key 在 WSL `~/.config/subfinder/provider-config.yaml`（或 `-pc` 指定），**与 Windows `.env` 完全分开、不自动同步**。框架默认调用不注入该文件；要用付费来源需自行在 WSL 配置并承担配额。
- 通用 Bash 变量与 `run_logged` 见 [索引](README.md)；占位 `ROOT/OUT` 运行前替换为批准目标。

## 3. 输入准备与场景命令

### 3.1 单 root（框架同款，文本输出）

```bash
run_logged subfinder subfinder -d "$ROOT" -silent -duc -o "$OUT/subdomains.txt"
```

- 环境/前置：WSL、PATH 已含 `~/asm-ws/bin`；`$ROOT` 为批准的注册域。
- 参数：`-d` 目标域；`-silent` 只输出子域；`-duc` 关闭更新检查；`-o` 输出文件。
- 输出：`$OUT/subdomains.txt`；`$OUT/subfinder.rc`。
- 预期：exit 0，每行一个子域（可能为空）。
- 失败判定：rc≠0、stderr 报错、或输出缺失；空文件要区分“来源成功但无结果”与“来源被限流/无 key”。

### 3.2 单 root 保留来源标签（JSONL）

```bash
run_logged subfinder-sources subfinder -d "$ROOT" -oJ -cs -duc -o "$OUT/subfinder-sources.jsonl"
```

- 参数：`-oJ` 输出 JSONL；`-cs` 在 JSON 里带 `sources`（注意 `-cs` 仅在 `-oJ` 时有效）。
- 输出：`$OUT/subfinder-sources.jsonl`，逐行 JSON 对象。
- 用途：比对“哪个来源贡献了哪个子域”，人工核对独立来源数。

### 3.3 批量 root（限速/限时）

```bash
run_logged subfinder-batch subfinder -dL "$OUT/domains.txt" -oJ -cs -rl 5 -timeout 15 -max-time 5 -duc -o "$OUT/subfinder-batch.jsonl"
```

- 参数：`-dL` 域名列表文件；`-rl` 全局每秒 HTTP 请求上限；`-timeout` 单请求超时秒数；`-max-time` 整个枚举分钟上限。
- 预期：按输入逐 root 产出；超时可能截断（部分结果），需结合 stderr 与行数判断是否完整。
- 失败判定：rc≠0 或行数明显少于单跑且 stderr 有超时/429。

### 3.4 只列可用来源（不采集）

```bash
run_logged subfinder-list subfinder -ls
```

- 输出：来源清单（`-oJ` 可得 JSON）。用于核对当前二进制内置了哪些来源、哪些需要 key。

## 4. 原生输出格式与解析

- **文本（框架用）**：每行一个子域。脱敏样例：

  ```text
  api.authorized.invalid
  mail.authorized.invalid
  ```

- **JSONL（`-oJ -cs`）**：逐行对象，关键字段 `host`、`source`/`sources`（随版本字段名以本机实际输出为准）。脱敏样例：

  ```json
  {"host":"api.authorized.invalid","sources":["crtsh","alienvault"]}
  ```

- **解析方法**：文本按行读取；JSONL 逐行 `json.loads`（**不是**整体 JSON 数组）。入库前用项目 `normalize_host` 规则：小写、去末尾点、IDNA 转 ASCII；范围用 `host == root or host.endswith("." + root)` 过滤。

## 5. 结果衔接与入库

- 衔接：子域 → Stage 5（dnsx/dig 解析出 A/AAAA，过滤 fake-IP 后得 selected）→ Stage 6（nmap/masscan 对批准 IP 扫端口）→ Stage 7（Web/截图）。
- 入库：经 Stage 4 入库 `domains`，来源 `subfinder`；人工 JSONL 不自动入库，需走 Stage 或另写适配器。
- 同提供商经 subfinder 与 OneForAll 重复取得同一域名，**不算**两份独立归属证据（见索引总则）。

## 6. 去重、来源与复核

- 去重键：标准化完整域名（小写、去末尾点、IDNA）；不同子域分别保留；`*.` 前缀剥离后判定。
- 来源保留：`-cs` JSONL 保留来源列表；框架合并到 `domains.sources`（逗号并集）。
- 时间戳：框架记录 first_seen/last_seen；人工运行保存 `started-utc.txt` 与 rc。
- 独立复核：用 `-ls` 核来源、用 `-oJ -cs` 对照来源数；与 dnsx/dig 结果交叉验证子域是否真实可解析。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| 返回空 | 看 stderr 的来源/超时/凭据日志；不能直接判“无子域” |
| 某提供商 429 | 降 `-rl`；用 `-rls <provider>=<rate>` 按提供商限额；检查是否需 key |
| 结果很少 | 是否只跑了默认来源；`-all` 慢但更全（需权衡配额）；无 key 来源被跳过 |
| 版本参数差异 | 以本机 `subfinder -h` 为准（2.17.0）；新版 flag 名可能变化 |
| 代理/网络 | `-proxy` 支持 HTTP 代理；WSL localhost 代理不镜像，需用可达代理地址 |
| fake-IP | 本步只产域名，解析问题交 Stage 5，不在此处处理 |

## 8. 官方来源与核对记录

- 官方仓库核对：[projectdiscovery/subfinder](https://github.com/projectdiscovery/subfinder)；版本 2.17.0 与 [tool-lock.json](../../tools/tool-lock.json) 的 release URL/SHA-256 一致。
- 本机证据：`subfinder -h` 原文 `data/validation/reference-help/subfinder.txt`；调度参数见 [s4_subdomain.py](../../asm/stages/s4_subdomain.py)（`-d root -silent -duc -o ...`，超时 `limits.subfinder_timeout` 默认 900s，幂等缓存）。
- 待验证：各提供商 key 配置后的实际覆盖率；公网来源可达性（当前未做带 key 实网验收）。

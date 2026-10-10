# Censys（网络空间测绘）

> 状态：**只有适配器（Legacy Search v2），未迁移 Platform v3，未接主流程，未带账户验收**
> 版本/接口：当前代码用 `https://search.censys.io/api/v2/hosts/search`（Legacy）；官方新版为 Platform `api.platform.censys.io/v3/`
> 凭据：`.env` 的 `CENSYS_ID` + `CENSYS_SECRET`（Legacy Basic auth）；**新 PAT 不能直接填进旧 secret 当支持**
> 核对日期：2026-10-10（源码核对；官方迁移指南核对）
> 证据：[asm/panel/censys.py](../../asm/panel/censys.py)、[官方迁移指南](https://docs.censys.com/docs/platform-api-transition-guide)

## 1. 用途、场景与局限

- **用途**：搜索主机/服务/证书，提取 IP 上各服务与 HTTP 标题。
- **适用场景**：未来补充资产线索；当前仅 Legacy 适配器+离线解析测试。
- **局限**：**Legacy v2 与 Platform v3 是两套认证与接口**；当前代码只实现 Legacy。查询与可用权限须在账户核对，**不要把新平台报错当成 key 输错**。
- **接入状态**：Legacy 适配器存在；离线解析经 `tests/unit/test_panel.py` 验证；无实网验收。

## 2. Legacy v2 与 Platform v3（关键区分）

| 维度 | 当前代码（Legacy v2） | 官方 Platform v3 |
|---|---|---|
| 端点 | `https://search.censys.io/api/v2/hosts/search` | `https://api.platform.censys.io/v3/...` |
| 认证 | Basic auth（`CENSYS_ID`/`CENSYS_SECRET`） | PAT + API Access role |
| 查询接口 | `GET hosts/search`（`q`/`per_page`/`cursor`） | `POST global/search/query` |
| 分页 | `cursor`（`result.links.next`） | 新版分页机制 |
| 状态 | 已实现（未验收） | **未实现，迁移待做** |

迁移需**同时**改认证、URL、查询/分页与响应解析，再重新验收；此批只记录缺口（见 COVERAGE panel 行）。

## 3. .env、认证与限速

```dotenv
CENSYS_ID=<Legacy API ID>
CENSYS_SECRET=<Legacy API Secret>
```

- 认证（Legacy）：HTTP Basic（`ID`:`SECRET`）。
- 限速/配额：项目持久 RateLimiter（默认 min_interval=1s、daily=200）；429 按 `Retry-After` 退避一次。账本：`python -m asm quota --profile customer`。
- 为空自动跳过；不实现 Platform PAT。

## 4. 输入准备与场景命令

**前置**：PowerShell 7、仓库根目录；已创建 profile、配置批准范围与 `.env`（Legacy `CENSYS_ID`+`CENSYS_SECRET`）。

```powershell
# 离线核对（不发账户请求）
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer

# 人工独立调用（仅当账户仍有 Legacy 权限）：改下面两行，运行 api.md 的同一段管道
# ENGINE = 'censys'; OPTIONS = {'max_pages': 1}
# QUERY = 'ip:192.0.2.10'
```

### 4.1 查询语法

```python
QUERY = 'ip:192.0.2.10'
```

适用查询（Legacy v2 语法，按需替换占位）：

| 场景 | 查询示例 |
|---|---|
| IP | `ip:192.0.2.10` |
| 域名/证书 | `parsed.names:authorized.invalid`（证书） |
| 服务 | `services.service_name:HTTP` |
| 标题 | `services.http.response.html_title:"登录"` |

> 注：Legacy 查询语法与 Platform v3 不同；迁移后需改写。

## 5. 接口、分页与额度

- `GET /api/v2/hosts/search`；Basic auth；参数 `q`、`per_page=100`、`cursor`（翻页）。
- 分页：`result.links.next` 提供下一页 cursor；默认最多 `max_pages`（当前 10）。
- 响应：JSON；`result.hits`（或兼容的 `data.hits`）数组，每项含 `ip` 与 `services`。

## 6. 输出格式与解析

`parse()` 对每个 hit 的每个 service 生成观测：`ip`→host、`service.port`、`service.transport_protocol`→proto（小写）、`service.service_name`→service、`service.http.response.html_title`→title。脱敏观测样例：

```json
{"host":"203.0.113.10","ip":"203.0.113.10","port":443,"proto":"tcp","service":"HTTPS","title":"Portal"}
```

**解析方法**：经 `Censys.parse()`；一台主机可产多条（每个 service 一条）。

## 7. 结果衔接与入库

- 衔接：Censys 资产 → 范围/时效核对 →（接入后）`assets`。
- 入库：人工 JSONL **不自动入库**；接入后经 `panel.ingest()` 入 `assets`。
- 同一 IP 多服务分别成记录。

## 8. 去重、来源与复核

- 去重键：`(host, port, proto)`。
- 来源保留：`source="censys"`（接入后）。
- 时间戳：观测 ts；配额按 UTC 日。
- 独立复核：与 DNS/端口复核交叉；区分 Legacy 与 Platform 响应结构。

## 9. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| HTTP 401/403 | ID/SECRET/权限；区分 Legacy 与 Platform 凭据 |
| 端点 404/结构变化 | 可能在用 Platform；旧代码只支持 Legacy |
| HTTP 429 | 额度/限速；查账本 |
| 返回空 hits | 成功但无结果；核对语法/权限 |
| 把 PAT 当 SECRET | Legacy 适配器不支持 PAT；需迁移实现 |

## 10. 官方来源与核对记录

- 官方文档核对：[Censys 平台迁移指南](https://docs.censys.com/docs/platform-api-transition-guide)；Legacy/Platform 的端点与认证差异以官方为准。
- 本机证据：[asm/panel/censys.py](../../asm/panel/censys.py)；离线测试 `tests/unit/test_panel.py`。
- 待验证：Legacy 在账户端的实际可用性与下线时间；Platform v3/PAT 的迁移实现与验收。

# Quake（360 网络空间测绘）

> 状态：**已自动调用**（Stage 4 域名收集）；**带账户搜索尚未验收**
> 版本/接口：`https://quake.360.net/api/v3/search/quake_service`
> 凭据：`.env` 的 `QUAKE_TOKEN`（空则跳过）
> 核对日期：2026-10-10（源码核对；官方入口核对）
> 证据：[asm/panel/quake.py](../../asm/panel/quake.py)、[官方入口](https://quake.360.net/quake/#/help)

## 1. 用途、场景与局限

- **用途**：搜索与目标域相关的公开资产（IP/domain/port/service/HTTP 标题/组件）。
- **适用场景**：Stage 4 子域与资产线索补充。
- **局限**：主流程**只调用单次 search**（不等于自动完整翻页）；`expanded_domain()` 子域拆分方法存在但**尚未被 Stage 4 自动使用**；不要把一页数据当全部结果。
- **接入状态**：主流程已用 Quake；HTTP 成功**仍需检查业务 code**（`code` 为 0 或 200 才视为成功）。

## 2. .env、认证与限速

```dotenv
QUAKE_TOKEN=<Quake API Token>
```

- 认证：请求头 `X-QuakeToken: <token>`（POST JSON）。
- 限速/配额：走项目持久 RateLimiter（默认 min_interval=1s、daily=200，可在 `rates.quake_*` 配置）；HTTP 429 时按 `Retry-After` 退避重试一次。账本：`python -m asm quota --profile customer`。
- 套餐/额度以账户为准；为空自动跳过。

## 3. 输入准备与场景命令

**前置**：PowerShell 7、仓库根目录；已创建 profile、配置批准范围与 `.env`（`QUAKE_TOKEN` 非空）。

```powershell
# 框架内场景（已接入主流程）
.\.venv\Scripts\python.exe -m asm stage 4 --profile customer --passive-only
.\.venv\Scripts\python.exe -m asm quota --profile customer

# 人工独立调用：改下面两行，运行 api.md 的同一段管道
# ENGINE = 'quake'; OPTIONS = {'size': 20, 'start': 0}
# QUERY = 'domain:"authorized.invalid"'
```

### 3.1 查询语法

```python
# Stage 4 使用
QUERY = 'domain:"authorized.invalid"'
```

适用查询（按需替换占位）：

| 场景 | 查询示例 |
|---|---|
| 域名 | `domain:"authorized.invalid"` |
| IP | `ip:"192.0.2.10"` |
| 证书 | `cert:"authorized.invalid"` |
| 标题 | `title:"登录"` |
| 正文 | `body:"特征文本"` |
| 组织 | `org:"批准的组织名"` |

人工独立调用遵循 [api.md](api.md)：`ENGINE='quake'`、`QUERY=...`、`OPTIONS={'size': 20, 'start': 0}`；需要下一批时单独保存并与上一批按 `(host,port,proto)` 去重（`{'size': 20, 'start': 20}`）。

## 4. 接口、分页与额度

- `POST /api/v3/search/quake_service`，请求体 `{"query","start","size"}`；`size` 上限 100。
- 分页：`start` 偏移 + `size` 条数；框架当前单次调用（`start=0`），**未自动翻页**。
- 响应：JSON；`code` 为 `"0"`/`200` 表示成功，`data` 为结果数组。

## 5. 输出格式与解析

`parse()` 从每项提取：`service.name`→service、`service.version`→version、`service.http.title`→title、`components`→product、`domain`/`http.host`/`hostname`/`ip`→host（多值取第一个）。脱敏观测样例：

```json
{"host":"api.authorized.invalid","ip":"203.0.113.10","port":443,"service":"https","title":"Portal","product":"[{\"name\":\"nginx\"}]","version":"1.24.0"}
```

**解析方法**：经 `Quake.parse()`；`components`/`server` 用 `joined()` 序列化为 JSON 字符串。归属核对需结合 DNS、服务与主体。

## 6. 结果衔接与入库

- 衔接：Quake 资产 → 范围过滤 → `domains`；服务事实由 Stage 5/6 复核。
- 入库：`panel.ingest()` 入 `assets`（键 `(host,port,proto)`），source 标 `quake`，exact 查询 confidence=A。
- 人工 JSONL 不自动入库，标 `candidate_only: true`。

## 7. 去重、来源与复核

- 去重键：`(host, port, proto)`；分页/多批结果按此合并。
- 来源保留：`source="quake"`；与其它来源重复不算独立证据。
- 时间戳：观测 ts；配额按 UTC 日。
- 独立复核：与 Stage 5 DNS、Stage 6 端口复核交叉；注意 Quake 数据可能是历史记录，需核对当前状态。

## 8. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| HTTP 401/403 | token/套餐/接口权限 |
| HTTP 200 但 code 非 0/200 | 业务层拒绝（语法/配额）；看 `message` |
| HTTP 429 | 套餐限速/本地限速；框架单次退避重试 |
| 返回空 | 区分“成功空结果”与“截断/语法错”；核对 `start/size` 与语法 |
| 结果截断 | 分批 `start` 递增，按 `(host,port,proto)` 去重合并 |
| 数据陈旧 | 核对当前 DNS/端口，不把历史记录当现状 |

## 9. 官方来源与核对记录

- 官方入口核对：[Quake 帮助](https://quake.360.net/quake/#/help)；请求头与接口路径以本机代码与官方入口为准。
- 本机证据：[asm/panel/quake.py](../../asm/panel/quake.py)（`search`、`expanded_domain`、`parse`）、[asm/panel/base.py](../../asm/panel/base.py)；离线解析测试 `tests/unit/test_panel.py`。
- 待验证：带账户真实搜索、完整翻页与子域拆分的实网行为。

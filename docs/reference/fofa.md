# FOFA（网络空间测绘搜索）

> 状态：**已接入工具层**（Stage 4、p2 与 Workbench）；缓存、字段降级与受控分页已用 MockTransport 离线验收，带账户搜索未在本轮实网验收。
> 版本/接口：`https://fofa.info/api/v1`（info/my + search/all）
> 凭据：`.env` 的 `FOFA_EMAIL` + `FOFA_KEY`（**两者必须同时配置**；空则跳过）
> 核对日期：2026-10-10（源码核对；官方 API 文档核对）
> 证据：[asm/panel/fofa.py](../../asm/panel/fofa.py)、[官方 API](https://fofa.info/api)

## 1. 用途、场景与局限

- **用途**：通过 FOFA 搜索发现与目标域/证书/组织相关的公开资产（host/ip/port/protocol/title/server）。
- **适用场景**：Stage 4 子域补充、p2 供应链的证书线索。
- **局限**：当前主流程**只调用一次 search**（不等于自动完整翻页）；`expanded_domain`/深度利用未全自动。归属需结合 domain、证书、页面主体、IP 范围核对；body 模糊匹配留隔离，**标题不等于归属**。
- **接入状态**：主流程已用 FOFA；原始完整 API 响应**尚未统一归档**（只存标准化观测）。

## 2. .env、认证与限速

```dotenv
FOFA_EMAIL=<FOFA 账号邮箱>
FOFA_KEY=<FOFA API Key>
```

- 认证：每次请求带 `email` + `key` 查询参数（GET）。**异常时的错误 URL 可能含认证参数，分享前必须脱敏**。
- 限速/配额：相邻请求间隔 **≥15 秒**、每 UTC 日 **≤200 次**（含失败、账户信息和 429 重试）；`rates.fofa_min_interval` 不能 <15、`rates.fofa_daily` 不能 >200（见 [conf.py](../../asm/conf.py)）。Workbench 按脱敏账户指纹使用共享 `data/account-rate-ledger.sqlite`，换项目或运行不清零；旧阶段保留旧项目账本。p2 证书另有默认最多 8 次的账本限制。账本查看不发请求。
- 账户信息默认启用，同一进程、同一账户 10 分钟内只请求一次；失败也缓存且不阻断搜索。`check_account=False` 可跳过它，但搜索请求仍须认证并经过限速/额度账本。
- **不能把 PAT/其它引擎 key 填入 FOFA 变量**；为空自动跳过，不会变成公共免费 API。

## 3. 输入准备与场景命令

**前置**：PowerShell 7、仓库根目录；已创建 profile、配置批准范围与 `.env`（`FOFA_EMAIL`+`FOFA_KEY` 同时非空）。

```powershell
# 框架内场景（已接入主流程）
.\.venv\Scripts\python.exe -m asm stage 4 --profile customer --passive-only
.\.venv\Scripts\python.exe -m asm quota --profile customer

# 人工独立调用：把下面三行改成本引擎后，运行 api.md 中的同一段管道
# ENGINE = 'fofa'; OPTIONS = {'max_pages': 1}
# QUERY = Fofa.domain_query('authorized.invalid')
```

### 3.1 查询语法（项目 helper）

当前代码用 FOFA dot syntax：

```python
from asm.panel.fofa import Fofa
# 域名查询（Stage 4 使用）
QUERY = Fofa.domain_query('authorized.invalid')
#   生成: domain="authorized.invalid" && title!="-" && title!="404"
# 证书 CN / 组织字段查询（p2 使用）
QUERY = Fofa.cert_query('authorized.invalid')                       # cert.subject.cn="..."
QUERY = Fofa.cert_query('批准的完整组织名', organization=True)        # cert.subject.org="..."
```

人工独立调用遵循 [api.md](api.md)：`ENGINE='fofa'`、`QUERY=...`、`OPTIONS={'max_pages': 1}`。适用查询（按需替换占位）：

| 场景 | 查询示例 |
|---|---|
| 域名 | `domain="authorized.invalid"` |
| IP | `ip="192.0.2.10"` |
| 证书 CN | `cert.subject.cn="authorized.invalid"` |
| 证书组织 | `cert.subject.org="批准的组织名"` |
| 标题 | `title="登录"` |
| 正文 | `body="特征文本"`（模糊，留隔离） |

## 4. 接口、分页与额度

- 流程：可选并缓存的 `GET /api/v1/info/my`，再循环 `GET /api/v1/search/all`。账户信息失败记录降级，搜索仍可继续；账户硬额度耗尽则不发送后续请求。
- 参数：`qbase64`、`page`（从 1 起）、`size`（默认 50，项目实现允许 1–1000）、`fields`（默认 `host,ip,port,protocol,title,domain,server`）。`fields` 支持字符串或列表，未知输出字段、空字段和缺少 host/domain/ip 的组合在发送前拒绝。
- 翻页：`max_pages` 默认 20，允许 1–200；Workbench 的项目计划通常更小。短页结束；页数、请求预算或账户额度到达上限时停止，并在 `panel.health` 标记 `truncated` 与原因。响应总量 `size/total` 只作为估计，不能把已收到一页说成已拉全。
- `max_requests` 为单次查询的物理请求预算（1–200），包含账户信息、429 重试和显式字段回退；默认 `min(200, max_pages + 1)`。每次物理请求仍经过持久限速器，查询预算不能绕过账户日限额。
- 响应 `error:true` 记录到 `panel.last_errors` 与 `panel.health.errors`，保留错误码和脱敏 `errmsg`，返回已得到的部分结果；如 `[820000]` 不被改写成成功空结果。可选 `fallback_fields=True` 仅把输出字段回退为基础字段，保留原失败并消耗相同预算，不改动查询字符串或账户权限。

### 4.1 拉全前的计划与停止纪律

先保存查询、输出字段、每页大小、页数上限、请求预算和本地账本剩余额度，再决定是否允许翻页。以 170/239/257 条等历史总量估计计划，不能为了凑总量追加请求。分页中的中断、429、字段拒绝和额度耗尽均须保留已有证据，报告如实标记覆盖不足。

```python
# 离线测试中的调用契约示例；本轮没有执行真实账户分页。
observations = list(panel.search(
    QUERY, size=50, max_pages=3, max_requests=4,
    fields=["host", "ip", "port", "protocol", "title", "domain", "server"],
    check_account=True, fallback_fields=False,
))
coverage = panel.health
errors = panel.last_errors
```

`truncated=False` 也不能独立证明互联网资产全集已覆盖；需结合保存的查询范围、数据源时间、总量估计和未采集能力说明。缓存保存脱敏账户指纹及健康摘要，不保存原始凭据。API 错误文本和返回字段在进入 Workbench 调用记录前移除认证值。

## 5. 输出格式与解析

标准化为 `Asset(host, ip, port, service=protocol, title, product=server)`；`asset_from()` 处理 `host` 缺省回退 `domain`、URL 解析、端口默认 443。脱敏观测样例（非原始响应）：

```json
{"host":"api.authorized.invalid","ip":"203.0.113.10","port":443,"service":"https","title":"Portal","product":"nginx"}
```

**解析方法**：经 `Fofa.parse()` 把 `fields` 与 `results` zip 成字典再生成 Asset；置信度由 `classify(query, exact=True)` 给定（含 `body` 的查询为 D 级）。

## 6. 结果衔接与入库

- 衔接：FOFA 资产 → `accept()` 范围过滤 → `domains`；IP/服务事实由 Stage 5/6 复核，不直接当确认资产。
- 入库：经 `panel.ingest()` 入 `assets`（键 `(host,port,proto)`），source 标 `fofa`，confidence 由查询类型决定（exact=A、body 模糊=D 入隔离）。
- 人工 JSONL（api.md 约定）**不自动入库**，标记 `candidate_only: true`。

## 7. 去重、来源与复核

- 去重键：`(host, port, proto)`；同键合并 source 并集。
- 来源保留：`source="fofa"`；与 subfinder/Quake 重复不算独立证据。
- 时间戳：观测 ts（UTC 秒）；配额账本按 UTC 日。
- 独立复核：结果与 Stage 5 DNS、Stage 6 端口复核交叉；`body` 命中必须在隔离区人工确认归属。

## 8. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| HTTP 401/403 | key/套餐/接口权限；不只看官网主页 200 |
| `error` 非空 | 查询语法或凭据；业务层拒绝（HTTP 可能 200） |
| HTTP 429 | `Retry-After`、本地限速与平台剩余额度；框架已单次退避重试 |
| 返回空 | 区分“成功但无结果”与“语法/额度/解析失败”；核对 fields 与语法 |
| TLS/连接超时 | DNS/代理/握手路径；主页可达不等于每次 API 成功 |
| 结果截断 | 提高 `max_pages`、拆分查询；注意本地 200/日 上限 |

## 9. 官方来源与核对记录

- 官方文档核对：[FOFA API](https://fofa.info/api)；端点与 `fields`/`qbase64` 用法与官方一致。
- 本机证据：[asm/panel/fofa.py](../../asm/panel/fofa.py)、[asm/panel/base.py](../../asm/panel/base.py)（RateLimiter：fofa min_interval≥15、daily≤200）、[asm/conf.py](../../asm/conf.py)（限额校验）；离线解析测试 `tests/unit/test_panel.py`。
- 本轮离线证据：`tests/unit/test_fofa_workbench.py` 验证同账户缓存/过期、账户失败仍搜索、字段验证与显式回退、820000 脱敏、分页截断、物理重试预算和账本不重置。执行日志为 `data/validation/fofa-workbench.xml`；MockTransport 不代表已完成真实账户搜索验收。
- 待验证：获准范围内的账户字段能力、真实分页完整性与服务端额度行为；本轮没有实网调用或读取现有 `.env`。

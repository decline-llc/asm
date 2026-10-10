# 搜索 API：通用调用、保存与排错

> 状态：主流程**自动调用 FOFA/Quake**；Hunter/ZoomEye/Shodan/Censys **只有适配器**（未接主流程路由）
> 凭据：Windows `.env`（与 WSL subfinder 的 `provider-config.yaml` **完全分开**，见下）
> 核对日期：2026-10-10（源码核对：[asm/panel/base.py](../../asm/panel/base.py) 与各引擎源码）
> 说明：本页是**人工独立调用约定**，不是新增的 `asm search` 命令，也不表示六家账户已实测通过。

## 1. 用途、场景与局限

- **用途**：在不改代码的前提下，用项目已有的引擎类做受控的人工搜索，并把结果以统一 JSONL 候选格式留存。
- **适用场景**：核对查询语法、评估数据时效、小批量补充线索。
- **局限**：**没有通用 `asm search`/`asm ingest` 命令**；人工 JSONL **不自动入库**、不升级置信度；保存的是**经解析+范围过滤的候选**，不是完整原始 API 响应（完整响应归档/自动路由待实现）。异常可能留下部分结果。

## 2. 接入状态、.env、认证与凭据边界

| 引擎 | .env 变量 | 认证方式（当前代码） | 主流程 |
|---|---|---|---|
| FOFA | `FOFA_EMAIL`、`FOFA_KEY` | GET 查询参数 `email`/`key` | 已接入（Stage 4 / p2） |
| Quake | `QUAKE_TOKEN` | 请求头 `X-QuakeToken` | 已接入（Stage 4） |
| Hunter | `HUNTER_KEY` | GET 查询参数 `api-key` | 仅适配器 |
| ZoomEye | `ZOOEYE_KEY` | 请求头 `API-KEY` | 仅适配器 |
| Shodan | `SHODAN_KEY` | GET 查询参数 `key` | 仅适配器 |
| Censys | `CENSYS_ID`、`CENSYS_SECRET` | Basic auth（Legacy v2） | 仅适配器 |

- **凭据只用占位符**，不写真实 key 进文档/日志/样例；**含 key 的 URL（FOFA/Hunter/Shodan）在日志与分享前必须脱敏**。
- **subfinder 的提供商 key 在 WSL `~/.config/subfinder/provider-config.yaml`**，与这里的 Windows `.env` **完全分开、不自动同步**（见 [subfinder.md](subfinder.md)）。
- 空变量自动跳过，不会变成公共免费 API。Censys 新 PAT 不能填进旧 `CENSYS_SECRET` 当支持（见 [censys.md](censys.md)）。

## 3. 场景命令：人工独立调用（PowerShell 7，仓库根目录）

> 前置：已创建 customer profile、配置批准范围与 `.env`；编辑 `ENGINE`/`QUERY`/`OPTIONS` 后运行。范围用 `passive_only=True` 只过滤域名归属、不发起主动探测。

```powershell
@'
import json, os
from dataclasses import asdict
from dotenv import load_dotenv
from asm.conf import load_config
from asm.db import Database
from asm.models import utcnow
from asm.scope import Scope
from asm.panel.fofa import Fofa
from asm.panel.quake import Quake
from asm.panel.hunter import Hunter
from asm.panel.zoomeye import ZoomEye
from asm.panel.shodan import Shodan
from asm.panel.censys import Censys
load_dotenv('.env')
ENGINE = 'fofa'
QUERY = Fofa.domain_query('authorized.invalid')
OPTIONS = {'max_pages': 1}
classes = {'fofa': Fofa, 'quake': Quake, 'hunter': Hunter,
           'zoomeye': ZoomEye, 'shodan': Shodan, 'censys': Censys}
required = {'fofa': ['FOFA_EMAIL', 'FOFA_KEY'], 'quake': ['QUAKE_TOKEN'],
            'hunter': ['HUNTER_KEY'], 'zoomeye': ['ZOOEYE_KEY'],
            'shodan': ['SHODAN_KEY'], 'censys': ['CENSYS_ID', 'CENSYS_SECRET']}
missing = [name for name in required[ENGINE] if not os.getenv(name)]
if missing:
    raise SystemExit('Missing variable names: ' + ', '.join(missing))
config = load_config('customer')
scope = Scope(config.data, passive_only=True)
directory = config.output / 'manual-api'
directory.mkdir(parents=True, exist_ok=True)
stamp = utcnow()
path = directory / (ENGINE + '-' + stamp.replace(':', '-') + '.jsonl')
with Database(config.output / 'asm.db') as db:
    panel = classes[ENGINE](db, config.data)
    try:
        with path.open('w', encoding='utf-8') as output:
            for asset in panel.search(QUERY, **OPTIONS):
                if not scope.contains(asset.host):
                    continue
                item = asdict(asset)
                item.pop('confidence', None)
                record = {'source': ENGINE, 'query': QUERY, 'observed_utc': stamp,
                          'candidate_only': True, 'asset': item}
                output.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as exc:
        # HTTP exception URLs can contain keys; print type only, retain partial observations.
        raise SystemExit(ENGINE + ': ' + type(exc).__name__ + '; check account/network/quota')
    finally:
        panel.close()
print(path.resolve())
'@ | .\.venv\Scripts\python.exe -
```

**关键行为**：`panel.search()` 经 `MappingEngine.request()` 发请求（带持久限速与 429 单次退避）；`scope.contains(asset.host)` 做范围过滤；`candidate_only: true` 明确这是候选而非确认资产；异常只打印异常类型（避免泄露含 key 的 URL）。输出 `data/customer/manual-api/<engine>-<UTC>.jsonl`。

## 4. 限速与配额

- 所有引擎共用项目持久 RateLimiter（默认 min_interval=1s、daily=200）；FOFA 强制 ≥15s、≤200/日（含失败与账户信息调用），见 [fofa.md](fofa.md)。
- 账本**按 profile 隔离**，不跨项目共享；查看 `python -m asm quota --profile customer`（不发请求）。
- 配额/套餐以各平台账户为准；本地限额是上限保护，不代表平台实际可用量。

## 5. 输出格式与保存

- **候选 JSONL**：每行 `{"source","query","observed_utc","candidate_only":true,"asset":{...}}`。不是原始 API 响应。
- **解析方法**：逐行 `json.loads`；`asset` 字段与 `models.Asset` 对应。
- **脱敏**：样例与日志中的 key/令牌用占位符；真实目标域名可保留（属授权范围）。

## 6. 错误分类（区别于“空结果”）

| 类别 | 表现 | 处理 |
|---|---|---|
| HTTP 错误 | 401/403/404/500 等 | 查 key/套餐/接口版本；401/403 不通过缩短限速解决 |
| 业务错误 | HTTP 200 但响应 `code`/`error` 非成功 | 看 message；语法或账户拒绝 |
| 限速 | HTTP 429 | 看 `Retry-After`、本地限速与平台剩余额度 |
| 成功但空 | 结果数组为空 | 核对语法、分页、平台数据时效、scope 过滤 |
| 结果截断 | 达到每页上限但未翻完 | 提高 `max_pages` 或分批 `start`/`page`/`cursor` |
| TLS/连接超时 | 握手/超时 | 查 DNS/代理/握手路径；主页可达不等于 API 成功 |

## 7. 结果衔接、去重与复核

- 衔接：候选 → 人工核对 → 必要时有正式适配器/Stage 接入后入库。
- 复核：与 Stage 5 DNS、Stage 6 端口复核交叉；搜索结果**不直接**写成确认资产或漏洞。
- 独立验证：`python -m pytest tests/unit/test_panel.py -q` 离线验证六家解析/分页逻辑（不发请求）。

## 8. 常见失败与排错

见上表“错误分类”。补充：多家同时失败先查本机网络/代理与 DNS；单家失败查该家 key/套餐/接口变化（接口迁移如 Censys Legacy→Platform）。

## 9. 官方来源与核对记录

- 依据源码：[asm/panel/base.py](../../asm/panel/base.py)（RateLimiter、MappingEngine.request、ingest）、各引擎源码（fofa/quake/hunter/zoomeye/shodan/censys）。
- 命令入口详见 [asm.md](asm.md)；各引擎查询语法/字段见各自专页。
- 待验证：六家真实账户的语法/字段/分页/配额；Censys Platform v3 迁移。

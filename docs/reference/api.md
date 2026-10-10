# 搜索 API：独立调用与结果保存

主流程当前自动用 FOFA/Quake，其它四家只有适配器。下例是本项目 Python 类的人工调用约定，不是新增 asm search 命令，也不表示六家账户已实测通过。各家查询语法、环境变量、OPTIONS 见专页。

在 PowerShell 7、仓库根目录执行。先创建 customer profile、配置批准范围和 .env，再编辑 ENGINE/QUERY/OPTIONS；空 key 不会变成公共免费 API。

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

保存的是经过解析和范围过滤的候选 JSONL，不是完整原始 API 响应；不自动导入资产或升级置信度。异常可能留下部分结果，需记录返回码和采集状态。完整响应归档、脱敏与自动适配器路由仍需另行实现。

FOFA 至少先调用一次账户接口，仍受 ≥15 秒/每项目 UTC 日≤200 请求限制；其它引擎也使用本项目持久限速/配额。不同 profile 不共享账本。查询额度：`python -m asm quota --profile customer`，不发网络请求。

| 情况 | 核对 |
|---|---|
| 401/403 或业务拒绝码 | key/套餐/API 权限/接口版本；不只看主页 200 |
| 429 | Retry-After、本地限速与平台剩余额度 |
| 空结果 | 查询语法、分页、平台数据时效、scope 过滤 |
| TLS/连接超时 | DNS/代理/握手路径；本机 HTTPS 可达不等于每次 API 成功 |
| 需要分享错误 | HTTP 错误 URL 可能含认证参数，先脱敏再分享 |

离线解析验证：`python -m pytest tests/unit/test_panel.py -q`。依据：[base.py](../../asm/panel/base.py) 和各引擎源码；命令入口详见 [asm.md](asm.md)。

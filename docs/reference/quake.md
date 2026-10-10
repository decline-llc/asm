# Quake

QUAKE_TOKEN；Stage 4 已使用，带账户搜索尚未验收。主流程目前调用单次 search，不等于自动完整翻页。

```powershell
.\.venv\Scripts\python.exe -m asm stage 4 --profile customer --passive-only
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

独立调用见 [api.md](api.md)：

```python
ENGINE = 'quake'
QUERY = 'domain:"authorized.invalid"'
OPTIONS = {'size': 20, 'start': 0}
# 需要下一批时单独保存，与上一批按 host/port/proto 去重
# OPTIONS = {'size': 20, 'start': 20}
```

当前 POST quake_service，X-QuakeToken header，size 最多 100；HTTP 成功仍需检查业务 code。expanded_domain 存在子域拆分方法，尚未由 Stage 4 自动使用；不要把一页数据当全部结果。

保存 IP/domain/port/service/HTTP title/components，范围过滤后核对 DNS、服务和主体。空 token 跳过；429/套餐限制、数据旧记录与网络问题分别处理。依据：[quake.py](../../asm/panel/quake.py)、[官方入口](https://quake.360.net/quake/#/help)。

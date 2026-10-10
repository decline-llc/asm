# ZoomEye

ZOOEYE_KEY；当前代码使用 api.zoomeye.ai/v2/search，只有适配器，未接主流程/未带账户验收。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

人工调用见 [api.md](api.md)：

```python
ENGINE = 'zoomeye'
QUERY = 'domain="authorized.invalid"'
OPTIONS = {'max_pages': 1}
```

POST、API-KEY header、qbase64/page/pagesize=100，当前请求字段 ip/port/domain/title/service/app/version。此处记录的是项目当前参数，不宣称套餐和接口无变化；账户侧需核对支持字段/语法。

解析后核对范围、主体、服务时效；分页结果按 host/port/proto 合并，不能按 IP 吞并域名。返回结构变化先保留脱敏样例修适配器，不把解析空当实际空。依据：[zoomeye.py](../../asm/panel/zoomeye.py)。

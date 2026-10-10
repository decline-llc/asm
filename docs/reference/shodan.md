# Shodan

SHODAN_KEY；适配器已做离线解析，主流程路由未接，真实账户权限待验证。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

人工调用见 [api.md](api.md)：

```python
ENGINE = 'shodan'
QUERY = 'hostname:authorized.invalid'
OPTIONS = {'max_pages': 1}
```

当前 GET /shodan/host/search、query/page、每页判断 100 条、最多 10 页。保存 ip_str/hostnames/port/transport/product/version/HTTP，hostnames 多值目前只选首个，这是适配器覆盖限制。

历史服务观测需核对当前 DNS/端口；TCP/UDP 单独保存，banner 不能自动确认组织归属。HTTP 错误 URL 可能带 key，分享前脱敏；查询权限/配额需在实际账户核对。依据：[shodan.py](../../asm/panel/shodan.py)。

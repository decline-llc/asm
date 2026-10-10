# Censys

当前 CENSYS_ID/CENSYS_SECRET 是 Legacy Search v2 Basic auth 适配器；未迁移 Platform v3，未接主流程，也未带账户验收。新 PAT 不能直接填进旧 secret 后视为支持。

```powershell
# 当前离线解析/分页逻辑验证，不发账户 API 请求
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

仅在账户仍有可用 Legacy 权限时，人工调用遵循 [api.md](api.md)：

```python
ENGINE = 'censys'
QUERY = 'ip:192.0.2.10'
OPTIONS = {'max_pages': 1}
```

旧适配器 GET search.censys.io/api/v2/hosts/search，q/per_page=100/cursor；保存 IP 的各 services 和 HTTP 标题。查询及可用权限须在账户核对，不把新平台报错当作 key 输错。

官方 Platform 使用 api.platform.censys.io/v3/、PAT 和 API Access role，旧 GET hosts/search 映射新 POST global/search/query。迁移需同时改认证、URL、查询/分页及响应解析，然后重新验收；此批只记录缺口。

依据：[censys.py](../../asm/panel/censys.py)、[官方迁移指南](https://docs.censys.com/docs/platform-api-transition-guide)。

# Hunter

HUNTER_KEY；有响应适配器，尚未接入主流程引擎路由。填 key 不会自动增加 Stage 4 数据。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer
```

人工调用 [api.md](api.md) 的当前代码约定：

```python
ENGINE = 'hunter'
QUERY = 'domain="authorized.invalid"'
OPTIONS = {'max_pages': 1}
```

GET openApi/search；query URL-safe Base64，page/page_size=100；解析 data.arr。由适配器编码，不手动在日志输出带 api-key URL。实际语法/账户/接口可用性仍需账户现场校验。

保存域名/IP/端口/标题/组件并范围核对；业务 code 拒绝与空 arr 分开。遇到 401/403 查权限，429 查额度；人工 JSONL 不会自动入库。依据：[hunter.py](../../asm/panel/hunter.py)。

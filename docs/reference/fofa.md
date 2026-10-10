# FOFA

当前主流程 Stage 4、p2 证书线索会使用。变量 FOFA_EMAIL/FOFA_KEY 必须同时配置；认证搜索尚未实网验收。

```powershell
.\.venv\Scripts\python.exe -m asm stage 4 --profile customer --passive-only
.\.venv\Scripts\python.exe -m asm quota --profile customer
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
```

人工独立调用按 [api.md](api.md) 设置：

```python
ENGINE = 'fofa'
QUERY = Fofa.domain_query('authorized.invalid')
OPTIONS = {'max_pages': 1}
# 证书 CN / 组织字段由项目 helper 生成
QUERY = Fofa.cert_query('authorized.invalid')
# QUERY = Fofa.cert_query('批准的完整组织名', organization=True)
```

当前接口先 info/my，再 search/all；每页 50、默认最多 20 页，但受本地请求限额和账户能力限制。≥15 秒、每项目 UTC 日≤200 次包括失败/账户请求；p2 证书另有默认最多 8 次的账本限制。

归属核对使用 domain、证书、页面主体及 IP 范围；body 模糊匹配留隔离，标题不等于归属。输出是标准化资产观测，原始完整响应尚未统一归档。请求异常可能带认证 URL，分享前脱敏。

空 key 自动跳过；返回空先核对语法/额度；账户拒绝不通过缩短限速解决。依据：[fofa.py](../../asm/panel/fofa.py)、[官方 API](https://fofa.info/api)。

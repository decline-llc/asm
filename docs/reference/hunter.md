# Hunter（奇安信网络空间测绘）

> 状态：**只有适配器，未接入主流程引擎路由**；填 key 不会自动增加 Stage 4 数据
> 版本/接口：`https://hunter.qianxin.com/openApi/search`
> 凭据：`.env` 的 `HUNTER_KEY`（空则跳过）
> 核对日期：2026-10-10（源码核对；接口以代码为准，账户侧未验收）
> 证据：[asm/panel/hunter.py](../../asm/panel/hunter.py)

## 1. 用途、场景与局限

- **用途**：搜索与目标域相关的公开资产（域名/IP/端口/标题/组件）。
- **适用场景**：未来补充 Stage 4；当前仅适配器+离线解析测试。
- **局限**：**未接主流程**；实际语法/账户/接口可用性需账户现场校验。`api-key` 在 URL 查询参数里，**日志/分享必须脱敏**。
- **接入状态**：响应适配器存在；离线解析经 `tests/unit/test_panel.py` 验证；无实网验收。

## 2. .env、认证与限速

```dotenv
HUNTER_KEY=<Hunter API Key>
```

- 认证：`GET` 查询参数 `api-key=<key>`（**URL 含 key，注意脱敏**）。
- 限速/配额：走项目持久 RateLimiter（默认 min_interval=1s、daily=200；`demo.yaml` 示例把 `hunter_daily` 设为 500，可按套餐调整）；429 按 `Retry-After` 退避一次。账本：`python -m asm quota --profile customer`。

## 3. 输入准备与场景命令

**前置**：PowerShell 7、仓库根目录；已创建 profile、配置批准范围与 `.env`（`HUNTER_KEY` 非空）。**注意 `api-key` 在 URL 中，日志需脱敏**。

```powershell
# 离线核对（不发账户请求）
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer

# 人工独立调用：改下面两行，运行 api.md 的同一段管道
# ENGINE = 'hunter'; OPTIONS = {'max_pages': 1}
# QUERY = 'domain="authorized.invalid"'
```

### 3.1 查询语法

```python
QUERY = 'domain="authorized.invalid"'
```

适用查询（按需替换占位；实际语法以账户端 Hunter 文档为准）：

| 场景 | 查询示例 |
|---|---|
| 域名 | `domain="authorized.invalid"` |
| IP | `ip="192.0.2.10"` |
| 证书 | `cert="authorized.invalid"` |
| 标题 | `web.title="登录"` |
| 正文 | `web.body="特征文本"` |

## 4. 接口、分页与额度

- `GET /openApi/search`；参数 `api-key`、`search`（**URL-safe Base64** 编码的查询）、`page`（从 1）、`page_size=100`、`is_web=0`。
- 分页：默认最多 `max_pages`（当前 10）；当页 `data.arr` 长度 <100 时停止。
- 响应：JSON；`code` 为 `200`/`0`/`None` 视为成功；结果在 `data.arr` 数组。

## 5. 输出格式与解析

`parse()` 从每项提取：`url`/`domain`→host、`ip`、`port`、`web_title`→title、`protocol`→service、`component`→tech（JSON 序列化）。脱敏观测样例：

```json
{"host":"api.authorized.invalid","ip":"203.0.113.10","port":443,"service":"https","title":"Portal","tech":"[{\"name\":\"nginx\"}]"}
```

**解析方法**：经 `Hunter.parse()`；业务 `code` 拒绝与“`arr` 为空”要分开处理（前者是失败，后者是成功但无结果）。

## 6. 结果衔接与入库

- 衔接：Hunter 资产 → 范围过滤 →（接入后）`domains`；服务事实由 Stage 5/6 复核。
- 入库：人工 JSONL **不自动入库**；接入主流程路由后才会经 `panel.ingest()` 入 `assets`。

## 7. 去重、来源与复核

- 去重键：`(host, port, proto)`。
- 来源保留：`source="hunter"`（接入后）；人工记录标 `candidate_only: true`。
- 时间戳：观测 ts；配额按 UTC 日。
- 独立复核：与 DNS/端口复核交叉；分页结果合并去重后对照数量。

## 8. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| HTTP 401/403 | key/权限 |
| HTTP 200 但 code 非 200/0 | 业务层拒绝；看 message |
| HTTP 429 | 额度/限速；查账本与套餐 |
| 返回空 arr | 成功但无结果；核对语法/范围 |
| URL 泄露 key | 日志与分享前脱敏 `api-key` |
| 语法不确定 | 以账户端 Hunter 最新文档为准，接口可能调整 |

## 9. 官方来源与核对记录

- 官方文档核对：Hunter 开放平台文档（账户端为准）；本机代码参数反映当前适配器实现。
- 本机证据：[asm/panel/hunter.py](../../asm/panel/hunter.py)、[asm/panel/base.py](../../asm/panel/base.py)；离线测试 `tests/unit/test_panel.py`。
- 待验证：真实账户的语法/字段/分页/配额；接入主流程的路由实现。

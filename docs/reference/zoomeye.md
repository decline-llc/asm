# ZoomEye（知道创宇网络空间测绘）

> 状态：**只有适配器，未接主流程/未带账户验收**
> 版本/接口：`https://api.zoomeye.ai/v2/search`（当前代码使用）
> 凭据：`.env` 的 `ZOOEYE_KEY`（空则跳过）
> 核对日期：2026-10-10（源码核对；接口以代码为准，账户侧未验收）
> 证据：[asm/panel/zoomeye.py](../../asm/panel/zoomeye.py)

## 1. 用途、场景与局限

- **用途**：搜索与目标域相关的公开资产（IP/端口/域名/标题/服务/应用/版本）。
- **适用场景**：未来补充 Stage 4；当前仅适配器+离线解析测试。
- **局限**：**未接主流程**；此处记录的是**项目当前参数**，不宣称套餐与接口无变化——账户侧需核对支持字段/语法。**不能按 IP 把域名吞并**（CDN/共享云）。
- **接入状态**：响应适配器存在；离线解析经 `tests/unit/test_panel.py` 验证；无实网验收。

## 2. .env、认证与限速

```dotenv
ZOOEYE_KEY=<ZoomEye API Key>
```

- 认证：请求头 `API-KEY: <key>`（POST JSON）。
- 限速/配额：项目持久 RateLimiter（默认 min_interval=1s、daily=200）；429 按 `Retry-After` 退避一次。账本：`python -m asm quota --profile customer`。

## 3. 输入准备与场景命令

**前置**：PowerShell 7、仓库根目录；已创建 profile、配置批准范围与 `.env`（`ZOOEYE_KEY` 非空）。

```powershell
# 离线核对（不发账户请求）
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer

# 人工独立调用：改下面两行，运行 api.md 的同一段管道
# ENGINE = 'zoomeye'; OPTIONS = {'max_pages': 1}
# QUERY = 'domain="authorized.invalid"'
```

### 3.1 查询语法

```python
QUERY = 'domain="authorized.invalid"'
```

适用查询（按需替换占位；实际语法以账户端 ZoomEye 文档为准）：

| 场景 | 查询示例 |
|---|---|
| 域名 | `domain="authorized.invalid"` |
| IP | `ip="192.0.2.10"` |
| 证书 | `cert="authorized.invalid"` |
| 标题 | `title="登录"` |
| 正文 | `body="特征文本"` |
| 组织 | `org="批准的组织名"` |

## 4. 接口、分页与额度

- `POST /v2/search`；请求头 `API-KEY`；请求体 `qbase64`（base64 查询）、`page`（从 1）、`pagesize=100`、`fields="ip,port,domain,title,service,app,version"`。
- 分页：默认最多 `max_pages`（当前 10）；当页 `data` 长度 <100 时停止。
- 响应：JSON；结果在 `data`（或旧结构 `matches`）数组。

## 5. 输出格式与解析

`parse()` 从每项提取：`domain`/`url`→host、`ip`、`port`（或 `portinfo.port`）、`title`（或 `portinfo.title`）、`service`、`app`→product、`version`。脱敏观测样例：

```json
{"host":"api.authorized.invalid","ip":"203.0.113.10","port":443,"service":"https","title":"Portal","product":"nginx","version":"1.24.0"}
```

**解析方法**：经 `ZoomEye.parse()`；**返回结构变化时先保留脱敏样例修适配器，不把解析空当实际空**。

## 6. 结果衔接与入库

- 衔接：ZoomEye 资产 → 范围/主体/服务时效核对 →（接入后）`domains`。
- 入库：人工 JSONL **不自动入库**；接入后经 `panel.ingest()` 入 `assets`。
- 分页结果按 `(host,port,proto)` 合并。

## 7. 去重、来源与复核

- 去重键：`(host, port, proto)`；不按 IP 吞并域名。
- 来源保留：`source="zoomeye"`（接入后）。
- 时间戳：观测 ts；配额按 UTC 日。
- 独立复核：与 DNS/端口复核交叉；注意历史数据的时效。

## 8. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| HTTP 401/403 | key/权限/套餐 |
| 业务层拒绝 | 看响应 message；区分 HTTP 错误与业务错误 |
| HTTP 429 | 额度/限速；查账本 |
| 返回空 | 区分成功空结果与解析失败；保留脱敏样例 |
| 接口字段变化 | 更新适配器前保留原始响应样例 |
| 结果截断 | 分页 `page` 递增，按键去重合并 |

## 9. 官方来源与核对记录

- 官方文档核对：ZoomEye API 文档（账户端为准）；本机代码参数反映当前适配器实现。
- 本机证据：[asm/panel/zoomeye.py](../../asm/panel/zoomeye.py)；离线测试 `tests/unit/test_panel.py`。
- 待验证：真实账户的字段/语法/分页/配额；`v2/search` 与历史接口的差异确认。

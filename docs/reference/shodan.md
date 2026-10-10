# Shodan（网络空间设备搜索）

> 状态：**只有适配器，主流程路由未接，真实账户权限待验证**
> 版本/接口：`https://api.shodan.io/shodan/host/search`
> 凭据：`.env` 的 `SHODAN_KEY`（空则跳过）
> 核对日期：2026-10-10（源码核对；接口以代码为准，账户侧未验收）
> 证据：[asm/panel/shodan.py](../../asm/panel/shodan.py)

## 1. 用途、场景与局限

- **用途**：搜索联网设备/服务（IP/端口/传输协议/产品/版本/HTTP 标题）。
- **适用场景**：未来补充资产与服务线索；当前仅适配器+离线解析测试。
- **局限**：**未接主流程**；历史服务观测需核对当前 DNS/端口；banner **不能**自动确认组织归属；`hostnames` 多值**目前只取首个**（适配器覆盖限制）。HTTP 错误 URL 可能带 key，分享前脱敏。
- **接入状态**：响应适配器存在；离线解析经 `tests/unit/test_panel.py` 验证；无实网验收。

## 2. .env、认证与限速

```dotenv
SHODAN_KEY=<Shodan API Key>
```

- 认证：`GET` 查询参数 `key=<key>`（**URL 含 key，注意脱敏**）。
- 限速/配额：项目持久 RateLimiter（默认 min_interval=1s、daily=200）；429 按 `Retry-After` 退避一次。账本：`python -m asm quota --profile customer`。

## 3. 输入准备与场景命令

**前置**：PowerShell 7、仓库根目录；已创建 profile、配置批准范围与 `.env`（`SHODAN_KEY` 非空）。**注意 `key` 在 URL 中，日志需脱敏**。

```powershell
# 离线核对（不发账户请求）
.\.venv\Scripts\python.exe -m pytest tests/unit/test_panel.py -q
.\.venv\Scripts\python.exe -m asm quota --profile customer

# 人工独立调用：改下面两行，运行 api.md 的同一段管道
# ENGINE = 'shodan'; OPTIONS = {'max_pages': 1}
# QUERY = 'hostname:authorized.invalid'
```

### 3.1 查询语法

```python
QUERY = 'hostname:authorized.invalid'
```

适用查询（按需替换占位）：

| 场景 | 查询示例 |
|---|---|
| 域名/主机名 | `hostname:authorized.invalid` |
| IP | `ip:192.0.2.10` |
| 证书 | `ssl.cert.subject.cn:authorized.invalid` |
| 标题 | `http.title:"登录"` |
| 正文/banner | `http.html:"特征文本"` 或 `product:nginx` |
| 组织 | `org:"批准的组织名"` |

## 4. 接口、分页与额度

- `GET /shodan/host/search`；参数 `key`、`query`、`page`（从 1）。
- 分页：默认最多 `max_pages`（当前 10，且硬编码上限 10）；当页 `matches` 长度 <100 时停止。
- 响应：JSON；结果在 `matches` 数组。

## 5. 输出格式与解析

`parse()` 从每项提取：`hostnames[0]`→host、`ip_str`→ip、`port`、`transport`→proto（TCP/UDP）、`_shodan.module`→service、`product`→product、`version`→version、`http.title`→title、`http.components`→tech（JSON 序列化）。脱敏观测样例：

```json
{"host":"api.authorized.invalid","ip":"203.0.113.10","port":443,"proto":"tcp","service":"https","product":"nginx","version":"1.24.0","title":"Portal"}
```

**解析方法**：经 `Shodan.parse()`；TCP/UDP 分开保存；多 hostname 只取首个（覆盖限制）。

## 6. 结果衔接与入库

- 衔接：Shodan 资产 → 核对当前 DNS/端口 →（接入后）`domains`/`assets`。
- 入库：人工 JSONL **不自动入库**；接入后经 `panel.ingest()` 入 `assets`。
- 历史观测必须与当前状态核对，不直接当现状。

## 7. 去重、来源与复核

- 去重键：`(host, port, proto)`；TCP/UDP 分开。
- 来源保留：`source="shodan"`（接入后）。
- 时间戳：观测 ts；配额按 UTC 日。
- 独立复核：banner/标题与当前实采交叉；归属需多证据，不能凭 banner 断言。

## 8. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| HTTP 401/403 | key/权限/套餐 |
| HTTP 429 | 额度/限速；查账本 |
| 返回空 matches | 成功但无结果；核对语法/范围 |
| URL 泄露 key | 日志与分享前脱敏 `key` |
| hostnames 为空 | 回退用 `ip_str` 作 host |
| 历史数据 | 核对当前 DNS/端口，不当现状 |

## 9. 官方来源与核对记录

- 官方文档核对：[Shodan API](https://developer.shodan.io/api)；端点与参数以官方与代码为准。
- 本机证据：[asm/panel/shodan.py](../../asm/panel/shodan.py)；离线测试 `tests/unit/test_panel.py`。
- 待验证：真实账户权限/配额；多 hostname 的覆盖改进；与当前状态的对照方法。

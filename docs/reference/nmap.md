# nmap（端口/服务识别）

> 状态：**已自动调用**（Stage 6 默认引擎；真实回环 TCP/UDP 已验收）
> 版本：7.94SVN（WSL apt）
> 位置：WSL `/usr/bin/nmap`
> 核对日期：2026-10-10（本机帮助核对：`data/validation/reference-help/nmap.txt`；回环实测：root nmap 发现 3 TCP + 1 UDP，见 ACCEPTANCE）
> 证据：本机 `nmap -h`、调度代码 [s6_port.py](../../asm/stages/s6_port.py)

## 1. 用途、场景与局限

- **用途**：对批准的 IP 做端口发现与服务/版本识别，产出资产事实（host/port/proto/service/product/version）。
- **适用场景**：Stage 6 端口基线；masscan 候选端口的服务复核；人工对单个/少量批准 IP 的核对。
- **局限**：只对**批准 IP** 使用；域名白名单不等于 IP 白名单。SYN（`-sS`）与 UDP（`-sU`）需要 root；无权限时用 `-sT`。UDP 的 `open|filtered` **不能**当确定开放。大段全端口扫描慢，需限速并单独保存。
- **接入状态**：Stage 6 默认引擎（`ports.engine` 缺省 nmap）；也作为 masscan 候选的服务确认步骤。人工 XML 不自动入库。

## 2. 实际接入状态

Stage 6 调用（root，后台）：`nmap [-6] -sS [-sU] -sV -sC -Pn -n --host-timeout 120s -p <T:端口,U:UDP端口> -oX {job}/nmap.xml <target>`。IPv6 目标自动加 `-6`。XML 由 `parse_nmap()` 解析：只取 `state="open"` 的端口，生成 `Asset(host=ip, ip=ip, port, proto, service, product, version, tech=extrainfo, source="nmap")` 入库。CDN 目标端口范围收窄为 `3000-9200`，非 CDN 默认 `1-65535`（`ports.tcp` 可配）。蜜罐判定：请求端口数 ≥1000 且全部开放时，记录 `honeypot` 并跳过后续探测。

## 3. 输入准备与场景命令

> 前置：WSL；目标必须是批准的具体 IP（占位 `$IP` 替换）。SYN/UDP 用 `sudo`；无 root 用 `-sT`。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 少量服务端口，XML 保留服务证据（无 root 用 -sT）
run_logged nmap nmap -sT -sV -Pn -n -p 80,443 -oX "$OUT/nmap.xml" "$IP"
# 框架同款：root SYN + 服务/默认脚本识别
run_logged nmap-syn sudo nmap -sS -sV -sC -Pn -n -p 80,443 -oX "$OUT/nmap-syn.xml" "$IP"
# 选定 UDP 服务（open|filtered 不等于确定开放）
run_logged nmap-udp sudo nmap -sU -sV -Pn -n -p 53,123 -oX "$OUT/nmap-udp.xml" "$IP"
# 批准主机的全 TCP 端口（限速，单独保存）
run_logged nmap-full sudo nmap -sS -sV -Pn -n -p 1-65535 --max-rate 100 -oX "$OUT/nmap-full.xml" "$IP"
# IPv6（占位符须替换为批准的 IPv6 地址）
run_logged nmap-ipv6 nmap -6 -sT -sV -Pn -n -p 80,443 -oX "$OUT/nmap-ipv6.xml" 2001:db8::10
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| `-sT -sV` | WSL 用户 | 批准 IP | `-sT` connect、`-sV` 版本、`-Pn` 不探活、`-n` 不解析、`-p` 端口、`-oX` XML | `$OUT/nmap.xml` | open 端口含 service | rc≠0；XML 无 host/state |
| `-sS -sC` | root | 同上 | `-sS` SYN、`-sC` 默认脚本 | `$OUT/nmap-syn.xml` | 更准的服务指纹 | 权限不足报错；换 `-sT` |
| `-sU` | root | 同上 | `-sU` UDP | `$OUT/nmap-udp.xml` | UDP open 记录 | `open|filtered` 不能当开放 |
| `-p 1-65535 --max-rate` | root | 同上 | `--max-rate` 限速 | `$OUT/nmap-full.xml` | 全端口清单 | 超时/丢包；重跑限速 |
| `-6` | WSL | 批准 IPv6 | `-6` | `$OUT/nmap-ipv6.xml` | v6 服务 | 地址族错误/不通 |

## 4. 原生输出格式与解析

XML（`-oX`）是事实源。脱敏片段：

```xml
<host><address addr="203.0.113.10" addrtype="ipv4"/>
<ports><port protocol="tcp" portid="443">
  <state state="open" reason="syn-ack"/>
  <service name="https" product="nginx" version="1.24.0" extrainfo="Ubuntu"/>
</port></ports></host>
```

**解析方法**：用 XML 解析器（项目 `parse_nmap()` 拒绝外部 DTD/实体）；只取 `state="open"`；键为 `host+port+proto`。字段：addr→host/ip；portid→port；protocol→proto；service 的 name/product/version/extrainfo。终端彩色输出不是解析依据。

## 5. 结果衔接与入库

- 衔接：nmap 开放端口 → 资产表；其中 `service in {http,https,ssl/http,http-proxy}` 或端口 80/443/8765 的 TCP 资产派生 URL → Stage 7 Web/截图。
- 入库：经 Stage 6 入 `assets`（键 `(host,port,proto)`）；UDP 与 TCP 分开。蜜罐判定后跳过。
- 人工 XML 不自动入库；masscan 的候选只有经 nmap 确认服务后才入库。

## 6. 去重、来源与复核

- 去重键：`(host, port, proto)`；TCP/UDP 分开；域名 host 与 IP host 不强行合并。
- 来源保留：`source="nmap"`；多次扫描同键合并来源、保留非空字段。
- 时间戳：入库 `ts`；原始 XML 与 job 目录保留采集时间。
- 独立复核：直接读 XML 对照数据库；UDP 结果与后续服务复核对照；总表不独列 proto 时回数据库/原始 XML 核。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| SYN/UDP 权限不足 | 框架以 root 运行；人工用 sudo 或 `-sT` |
| 目标无响应 | 区分 filtered/closed/timeout；查原始 XML，不只看终端 |
| 服务为空 | 保留端口候选；核对 `-sV`、返回内容与中间设备 |
| UDP 全 `open|filtered` | 不等于开放；需要服务级复核或延长等待 |
| 全端口都开 | 可能蜜罐；框架 `honeypot` 判定会跳过后续探测 |
| 版本参数差异 | 以本机 `nmap -h`（7.94SVN）为准 |

## 8. 官方来源与核对记录

- 官方文档核对：[nmap.org](https://nmap.org/book/man.html) 选项与本机 help 一致；版本以本机 `nmap --version` 7.94SVN 为准。
- 本机证据：`nmap -h` 原文 `data/validation/reference-help/nmap.txt`；调度/解析 [s6_port.py](../../asm/stages/s6_port.py)；回环验收见 ACCEPTANCE「真实 WSL/nmap」。
- 待验证：IPv6 主动端口链路的原生实测；公网目标在可信解析后的服务识别。

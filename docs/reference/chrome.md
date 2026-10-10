# WSL Google Chrome（浏览器运行时）

> 状态：**仅安装**（作为 gowitness 的浏览器运行时）；当前 ASM 截图主链用 Windows Playwright Chromium（见 [playwright.md](playwright.md)）
> 版本：155.0.8059.39
> 位置：WSL `/usr/bin/google-chrome`
> 核对日期：2026-10-10（版本清单核对：WSL `manifests/installed.txt`）
> 证据：[Chrome Headless 官方说明](https://developer.chrome.com/docs/chromium/headless)、本机版本清单

## 1. 用途、场景与局限

- **用途**：为 gowitness 提供真实浏览器内核；也可单独用 headless 模式做截图/DOM 导出核对。
- **适用场景**：gowitness 截图运行时；人工对回环 fixture 的渲染核对。
- **局限**：**单独 Chrome 命令不承担主流程的范围规则**——生产截图需要对导航和每个子资源请求限制范围。不要把 Windows 浏览器复制到 Linux。headless 截图/DOM 不自动进 ASM。
- **接入状态**：已安装、未接入主流程；是 gowitness 的依赖，不是独立调度工具。

## 2. 实际接入状态

无直接调度。gowitness 通过 `--chrome-path /usr/bin/google-chrome` 使用它。生产接入与范围控制随 gowitness 一并评估。

## 3. 输入准备与场景命令（WSL 回环 fixture 先行验证）

> 前置：WSL **普通用户**（不要用 root 直接跑以避免 sandbox 问题）；fixture 在 WSL 侧回环监听。不使用个人登录配置目录。通用变量/`run_logged` 见 [索引](README.md)。

```bash
# 查看版本
run_logged chrome-version /usr/bin/google-chrome --version
# headless 截图（本地运行中的 fixture）
run_logged chrome-shot /usr/bin/google-chrome --headless --screenshot="$OUT/chrome.png" --window-size=1280,720 http://127.0.0.1:8765
# headless 导出渲染后的 DOM
run_logged chrome-dom /usr/bin/google-chrome --headless --dump-dom http://127.0.0.1:8765
```

| 命令 | 环境 | 前置 | 关键参数 | 输出 | 预期 | 失败判定 |
|---|---|---|---|---|---|---|
| `--version` | WSL | — | — | stdout 文本 | 打印版本 | 命令不存在 |
| `--headless --screenshot` | WSL 用户 | 回环 fixture | `--screenshot=<path>`、`--window-size` | `$OUT/chrome.png` | PNG 图片 | rc≠0/白屏/超时 |
| `--headless --dump-dom` | WSL 用户 | 同上 | `--dump-dom` | `$OUT/chrome-dom.stdout.log` | 渲染后 DOM | 空/报错 |

## 4. 输出格式与解析

- `--screenshot` 产 PNG 图片；`--dump-dom` 产浏览器执行后的 HTML（stdout）。两者都**不自动进 ASM**。
- 解析：PNG 用图片工具核对尺寸；DOM 文本用于核对渲染结果是否含动态内容。

## 5. 结果衔接与入库

- 衔接：作为 gowitness 内核；单独的 PNG/DOM 用于人工核对。
- 入库：不自动入库；ASM 报告只内嵌 Playwright 已采集的 PNG。

## 6. 去重、来源与复核

- 去重键：N/A（工具输出文件按运行目录区分）。
- 来源保留：PNG/DOM 与 argv/rc 同目录留存。
- 时间戳：保存 `started-utc.txt` 与 rc。
- 独立复核：与 gowitness/Playwright 对同一 fixture 的截图对照渲染一致性。

## 7. 常见失败与排错

| 情况 | 判定与处理 |
|---|---|
| root/sandbox 错误 | 用 WSL 普通用户；不把“关闭 sandbox”当默认修复 |
| 缺运行库 | 核对部署/doctor；不复制 Windows 浏览器到 Linux |
| 白屏/超时 | 查 stderr、目标回环环境、TLS/代理与动态加载 |
| 无显示环境报错 | headless 不需要 X；确认未误加需显示的 flag |

## 8. 官方来源与核对记录

- 官方文档核对：[Chrome Headless 官方说明](https://developer.chrome.com/docs/chromium/headless)——`--headless`、`--screenshot`、`--dump-dom`、`--window-size` 与官方一致。
- 本机证据：版本 `155.0.8059.39` 记录于 WSL `manifests/installed.txt`（ACCEPTANCE 工具部署）。
- 待验证：gowitness 接入后的范围控制与稳定性；与 Playwright Chromium 渲染差异。

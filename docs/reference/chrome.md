# WSL Chrome

已安装 Google Chrome 155.0.8059.39，路径 `/usr/bin/google-chrome`。作为 gowitness 的浏览器运行时，当前 ASM 截图主链使用 Windows Playwright Chromium。

```bash
run_logged chrome-version /usr/bin/google-chrome --version
# WSL 普通用户、本地运行中的 fixture；不使用个人登录配置目录
run_logged chrome-shot /usr/bin/google-chrome --headless --screenshot="$OUT/chrome.png" --window-size=1280,720 http://127.0.0.1:8765
run_logged chrome-dom /usr/bin/google-chrome --headless --dump-dom http://127.0.0.1:8765
```

chrome-dom.stdout.log 是浏览器执行后的 DOM，chrome.png 是浏览器图片；这两者不自动进 ASM。生产截图需要对导航和每个子资源请求限制范围，单独 Chrome 命令不承担主流程的范围规则。

| 情况 | 处理 |
|---|---|
| root/sandbox 错误 | 用 WSL 普通用户，不把关闭 sandbox 当默认修复 |
| 缺运行库 | 核对部署/doctor，不复制 Windows 浏览器到 Linux |
| 白屏/超时 | 查 stderr、目标回环所在环境、TLS/代理与动态加载 |

依据：[Chrome Headless 官方说明](https://developer.chrome.com/docs/chromium/headless)、本机版本清单。

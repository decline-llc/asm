# 备用扫描器

`a_scan.py` 使用 Python 标准库，对上层已批准的 IP/端口做 TCP connect。经桥部署到 WSL `~/asm-ws/tools/a_scan.py`；不要在 Windows 安装扫描二进制。

它是端口层备用工具，输出 JSONL。Web 指纹和路由检查由 Windows 编排阶段负责。没有登录、默认口令尝试、漏洞利用或文件写入目标功能。

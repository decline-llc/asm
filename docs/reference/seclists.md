# SecLists

固定 2026.1/commit 190c6f7b，WSL `~/asm-ws/wordlists/SecLists`。当前稀疏检出 7 文件：README/LICENSE、top-5000 DNS 字典和 raft-medium directories/extensions/files/words。

```bash
git -C "$HOME/asm-ws/wordlists/SecLists" rev-parse HEAD
git -C "$HOME/asm-ws/wordlists/SecLists" sparse-checkout list
wc -l "$HOME/asm-ws/wordlists/SecLists/Discovery/DNS/subdomains-top1million-5000.txt"
wc -l "$HOME/asm-ws/wordlists/SecLists/Discovery/Web-Content/raft-medium-directories.txt"
# 需要另一份字典时扩展选择，不切换版本
git -C "$HOME/asm-ws/wordlists/SecLists" sparse-checkout add --no-cone Discovery/Web-Content/common.txt
```

完整安装入口见 RUNBOOK 的 ASM_SECLISTS_FULL=1；所需空间/下载显著增加，按实际需要选择。扩展可能触发网络 lazy-fetch；先保留本地改动，再核对版本/文件哈希，不直接覆盖字典内容。

字典是工具输入；它不是已发现资产。Stage 4 当前使用内置 DNS_PREFIXES，未自动读全部 SecLists；ffuf 原生调用由 -w 选择文件。不要把同名结果和输入字典互相覆盖。

| 情况 | 处理 |
|---|---|
| 文件找不到 | 看 sparse-checkout list，并核对大小写/路径 |
| 字典太大/运行太久 | 选择当前阶段需要的类型和规模，控制工具速率 |
| Git 请求超时 | 保留已经校验的文件/元数据，查 WSL HTTPS/代理路径 |

依据：[版本锁](../../tools/tool-lock.json)、[部署说明](../../tools/README.md)。

# 官方资料与版本出处

2026-10-09，通过 GitHub 官方 Releases API 核实当前固定版本，资产 URL 和 SHA-256 原样写入 `tools/tool-lock.json`。

- [ProjectDiscovery 官方工具](https://projectdiscovery.io/open-source)
- [subfinder releases](https://github.com/projectdiscovery/subfinder/releases)
- [dnsx releases](https://github.com/projectdiscovery/dnsx/releases)
- [httpx releases](https://github.com/projectdiscovery/httpx/releases)
- [naabu releases](https://github.com/projectdiscovery/naabu/releases)
- [nuclei releases](https://github.com/projectdiscovery/nuclei/releases)
- [katana releases](https://github.com/projectdiscovery/katana/releases)
- [ffuf releases](https://github.com/ffuf/ffuf/releases)
- [gowitness releases](https://github.com/sensepost/gowitness/releases)
- [FOFA API 与证书字段](https://fofa.info/api)
- [OneForAll v0.4.5](https://github.com/shmilylty/OneForAll/tree/v0.4.5)
- [OneForAll 固定版本 Collect 源码](https://github.com/shmilylty/OneForAll/blob/5ad26a99cd8625dfff0f3ce0300a10b38135b03a/modules/collect.py)（2026-10-10，同时读取本机相同 commit 的源码核对线程调度、模块选择与超时）
- [OneForAll 固定版本主流程](https://github.com/shmilylty/OneForAll/blob/5ad26a99cd8625dfff0f3ce0300a10b38135b03a/oneforall.py)（默认主流程存在 wildcard/SRV 与注册域处理，本项目使用隔离被动包装器）
- [OneForAll 固定版本 AlienVault 模块](https://github.com/shmilylty/OneForAll/blob/5ad26a99cd8625dfff0f3ce0300a10b38135b03a/modules/intelligence/alienvault.py)（两个端点赋值覆盖原结果；本项目进程内保留二者并集，离线真实工具测试验证）
- [SecLists 2026.1](https://github.com/danielmiessler/SecLists/tree/2026.1)
- [SecLists 固定 commit 递归 tree 与文件尺寸](https://api.github.com/repos/danielmiessler/SecLists/git/trees/190c6f7bd58c847ceadfe57d9853592737f059e8?recursive=1)
- [exrex 0.12.0 官方发布](https://pypi.org/project/exrex/0.12.0/)
- [Python 3.12 变更](https://docs.python.org/3.12/whatsnew/3.12.html)
- [dnsx 官方用法](https://docs.projectdiscovery.io/opensource/dnsx/usage)（2026-10-10；运行参数同时核对本机固定 1.3.1 帮助，仅请求 A/AAAA/MX/NS/CNAME）
- [dnspython Resolver 类](https://dnspython.readthedocs.io/en/stable/resolver-class.html)（2026-10-10；configure=False、指定 nameserver/port、lifetime 与 NXDOMAIN）

面板已做脱敏格式回放，真实 API 能否继续使用必须以账户现场验证为准。服务政策和接口可能变化，不根据旧返回样例宣称 live 验收完成。

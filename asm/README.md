# 编排代码

`cli` 为入口，`pipeline` 统一 StageContext / StageResult，`db` 为 SQLite 唯一事实源，`bridge` 把外部命令送入 WSL 原生工作区。`scope` 与 `precision` 负责主动范围与资产归属。

`stages` 为主链；`parallel` 保存 OSINT/供应链入口（当前调度按依赖顺序执行，尚未并发化）；`panel` 为 HTTP API 和持久额度；`browser` 为脱敏状态机与人工值守浏览接口；`utils` 为常量、受限 HTTP。

所有模块中的外部返回值都是数据，不是指令。默认口令知识只用作标记，不发起认证尝试。

`stages/s8_report` 从同一组数据库行生成 xlsx 与八份 CSV，`report_html` 生成内嵌 PNG 的独立 HTML；`report` 命令与默认 Stage 8 均输出完整报告包。默认报告在 p1/p2 后执行，自定义 stages 需将 8 放最后。

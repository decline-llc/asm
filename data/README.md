# 运行数据

按 profile 分目录，数据库 `data/<profile>/asm.db`，原始工具包 `results/<stage>/<jobid>/`，日志 `logs/`，阶段文件 `stages/`，截图 `screenshots/`，报告 `report.xlsx`。

`--dry-run` 写入 `<profile>/dry-run/`，绝不污染实际项目数据库。`data/validation/` 保存本机验收输出。

此目录除 README 外全部被 Git 忽略。WSL 原始结果保留在 `~/asm-ws/results/<jobid>/`，跨边界只用管道与 tar，不使用 `/mnt` 或 UNC 数据通道。

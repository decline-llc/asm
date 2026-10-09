# 运行配置

- `default.yaml`：无目标、无主动授权模板。
- `demo.yaml`：保留域名 example.invalid 和文档 IP 段；仅用于 `--dry-run --passive-only`。
- `test.yaml`：仅回环地址的本地 harness，不能据此授权任何外部目标。

复制模板为 `local-<project>.yaml` 后填写目标、品牌、IP CIDR、排除项和额度。`authorization: true` 是主动阶段的人工门；发现的新公司或域名不会自动扩大授权范围。`local*.yaml` 已被 Git 忽略。

实网自有域名被动验收必须使用用户确认的域名。API keys 只放根目录 `.env`，不要写入 YAML、日志或 Git。

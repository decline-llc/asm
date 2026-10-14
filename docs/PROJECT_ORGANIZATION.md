# 项目与历史证据整理

2026-10-11，Asia/Shanghai。

## 分类与目录

业务用途 `investigation / validation / demo` 与执行来源 `live / replay` 独立。正式调查可使用离线回放；使用企业证据进行软件恢复验收仍属于测试。

| 内容 | 位置 |
|---|---|
| 业务项目配置 | `profiles/investigations/local-<project>.yaml` |
| 测试配置 | `profiles/validation/local-<project>.yaml` |
| 演示配置 | `profiles/demo/local-<project>.yaml` |
| 业务状态数据库 | `data/workbench.sqlite` |
| 后续验收状态数据库 | `data/validation/workbench.sqlite` |
| 新交付证据 | `report/<分类>/<project>_delivery/runs/<run_id>/` |
| 目录整理备份与清单 | `data/organization/<时间戳>/` |

默认项目列表显示业务调查，测试及演示有单独分类。卡片、列表和表格共享同一数据与搜索条件，视图偏好保存在本地。项目名称、范围、最近运行、更新时间、运行数与交付状态为主要信息；配置路径放入详情。

新配置可显式写入 `project_purpose`。旧配置按已确认的验收命名或所在分类目录识别，普通本地项目和普通回放项目默认仍为业务项目。默认 `GET /api/projects` 返回业务调查；`?purpose=validation|demo|all` 可查看其他分类。

## 保留历史引用

当前已整理 18 份本机配置：业务配置 2 份、测试配置 16 份。数据库原有 15 个项目均为验收记录，分类后默认业务列表为空；前端仍提供实际历史调查档案入口及虚构演示入口。

`scripts/organize_projects.py` 默认只输出计划，`--apply` 应用目录整理。迁移前备份数据库，验证配置复制哈希，再更新项目配置路径，提交后移除旧配置副本。运行、步骤、事件、资产、证据记录等表在迁移前后验证内容哈希一致。历史报告和证据包保留原路径，已有配置的权限修订与内容不改写。

根目录 `default.yaml / demo.yaml / test.yaml / modes.yaml` 继续作为兼容模板及模式目录。CLI 可按短配置名查找分类目录，重名时要求完整路径。

## 历史证据页面

`?pilot=1` 直接打开独立的历史调查档案页，标题与数据均来自实际保存的调查对象。候选资产、DNS 观测、范围外线索、子域及台账各有分区；支持全文搜索、来源/上游筛选、排序、分页、表格/列表、详情与完整保存记录、筛选结果 CSV 和完整 HTML 报告。

历史页面使用原始静态证据模块及原报告导出器。候选、范围外线索及查询精度分别呈现，浏览详情不改变原始证据状态。

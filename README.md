# 短剧投放全流程自动化工作台

面向本地 Windows 运行的全流程自动化工作台：读取飞书剧目表、自动入队、提取番茄 IAA/IAP 链接、配置投放资源、生成并校验 PlanSpec、提交标准投放计划并回写完成状态，通过 Dashboard 提供统一视图。

## 本地启动

当前处于 Phase 0 仓库初始化阶段，一键启动脚本将在 Phase 1 提供。

预期运行形态：

1. 启动 FastAPI Control Server；
2. 启动 Automation Worker；
3. 构建并托管 Vue Dashboard（正式模式）或启动 Vite 开发服务器（开发模式）。

## 文档索引

- 设计文档：`docs/superpowers/specs/2026-08-06-short-drama-delivery-design.md`
- 实施计划：`docs/superpowers/plans/2026-08-06-short-drama-delivery-implementation.md`
- 前端 UI 子计划：`docs/plans/frontend-ui-development-plan.md`
- 文档总览：`docs/README.md`

> 架构、全流程、业务规则等专项文档将在 Phase 0 后续任务落盘，落盘后同步补充到 `docs/README.md`。

# Phase 10 交付总结：主链路接线与 Mock 全链路

## 范围

- 剧目扫描调度与自动入队：`DeliveryScheduler` + Control Server 调度线程
- Worker 执行循环：心跳 → 队列推进 → 领取 → 真实编排执行 → 事件/台账 → 完成/人工
- 账户块分配服务与账户概览：IAA 3+3+3+1、IAP 3+3、测试户默认 IAA-B4、分配预览 API
- Worker 真实编排执行器：链接提取 → 账户分配 → PlanSpec → 标准投放 → 完成

## 验收结果（2026-08-07）

- backend pytest：545 passed
- verify-phase9：single/three/five/ten 全 PASS
- verify-phase10：Mock 全链路 4 passed
- codegraph：275 files、4132 nodes、10489 edges（Phase 10 后已同步）

## Mock 全链路覆盖

- TOMATO：扫描 → 入队 → 领取 → 链接提取 → 账户分配 → 标准投放 → COMPLETED + 台账 + 事件；不写飞书 J/K/L。
- 账户全部占用：MANUAL_REVIEW + ERROR 事件，无台账。
- JUBIAN：暂返回 MANUAL_REVIEW，后续接入表内 J/K/L 链接。
- 默认 `WORKBUDDY_ALLOW_FINAL_SUBMIT=false`：本地流程 COMPLETED，提交被安全开关拦截并记录 WARNING 事件。

## 遗留项

- 真实链路：Playwright page、真实飞书账户表读取/回写、JUBIAN 表内链接、M=1 延迟写入/补偿。
- DRY_RUN 台账状态区分、`worker_executor.py` 拆分、账户表真实数据源。
- whole-branch review 的 Important 4-9（分层约束、规则闭环、完成幂等、并发原子、状态联动、前后端契约）待后续任务。

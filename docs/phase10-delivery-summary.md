# Phase 10 交付总结：生产链路加固与安全闭环

## 范围

- 剧目扫描调度与自动入队：`DeliveryScheduler` + Control Server 调度线程
- Worker 执行循环：心跳 → 队列推进 → 领取 → 真实编排执行 → 事件/台账 → 完成/人工
- 账户块分配：IAA 3+3+3+1、IAP 3+3、测试户 IAA-B4、条件整块写入、回读、追加块和同日 CID 唯一占用
- Worker 真实编排：E 时间到点准备并冻结链接 → 真实配置校验 → 账户分配 → DeliveryFormSpec → 标准投放 → 对账/轮询 → 完成

## 验收结果（2026-08-10）

- backend pytest：672 passed（最终全量检查）
- Phase 10：番茄真实编排 Mock、冻结快照零二次调用、Dry Run、账户不足、剧变直读全部通过
- Dashboard：Dry Run 显示为“演练完成”，不再映射成功

## Mock 全链路覆盖

- TOMATO：扫描 → 等待 E 时间 → 领取 → 提取并冻结 → 账户分配 → 标准投放 → COMPLETED + 台账 + 事件；真实模式回填 J/K/L，Dry Run 零写入。
- 账户全部占用：MANUAL_REVIEW + ERROR 事件，无台账。
- JUBIAN：直接冻结表内 J/K/L，不进入番茄。
- 默认 `WORKBUDDY_ALLOW_FINAL_SUBMIT=false`：终态为 DRY_RUN，无台账、无 M=1、无账户和链接远程写入。

## 上线前外部验收项

- 在实际登录态下复核三套页面选择器；当前代码会对缺失选择器安全失败，不会猜测点击。
- 为每部待投剧配置真实素材 ID、6 个标题包及 CID 映射后，再从单部 Dry Run 开始逐级验收。
- 前端主包仍有约 954 kB 的构建警告，本次不做无关拆包重构。

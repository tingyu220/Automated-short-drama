# 真实投放链路修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复真实 Worker 不可达、链接准备未接线、Mock 被误判完成、账户分配不落飞书、轮询与租约错误及结果不确定可重复提交等缺陷，使系统在 Dry Run 下绝不产生完成副作用，并为真实单任务投放建立可验证的安全闭环。

**Architecture:** Control Server 只负责扫描和持久化来源任务及 `WAITING_TIME` 队列；Automation Worker 严格在 E 时间到达并领取后执行一次链接准备，立即冻结快照，后续步骤只消费该快照。真实平台能力由显式运行模式和 Adapter 能力接口控制，账户分配采用“读取最新快照 → 生成意图 → 校验真实配置 → 条件写入 → 回读确认”，提交与轮询使用可恢复状态并持续续租。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite、Playwright、pytest；Vue 3、TypeScript、Vitest。

## Global Constraints

- 默认 `WORKBUDDY_ALLOW_FINAL_SUBMIT=false`；只有真实 Adapter、显式开启最终提交并通过配置校验时才允许提交。
- Dry Run 不写飞书 J/K/L、不写账户表、不写 M=1，不生成成功台账，不进入 `COMPLETED`。
- 剧变只读取飞书 J/K/L，不进入番茄；番茄链接只在准备阶段提取并冻结。
- 飞书账户表是账户唯一事实源；写前检查空值，整块写入后回读，部分成功进入 `PARTIAL_WRITE/MANUAL_REVIEW`。
- 轮询间隔 300 秒、最长 7200 秒；执行期间续租，不允许过期任务被重复领取。
- `RESULT_UNCERTAIN` 必须先按幂等键对账；未确认外部不存在前禁止重新提交。
- 不删除文件；不覆盖当前工作区中与本计划无关的未提交修改。
- 每个行为修改严格执行 pytest 的 RED → GREEN；提交前必须另行向用户确认，Commit Message 使用中文。

---

### Task 1: 恢复测试基线并固定时间依赖

**Files:**
- Modify: `backend/tests/integration/test_phase10_full_scenario.py`
- Modify: `backend/tests/integration/test_rule_full_scenario.py`
- Modify: `backend/tests/unit/test_plan_spec_service.py`
- Modify: `backend/src/backend/application/services/plan_spec_service.py`

**Interfaces:**
- Consumes: `PlanSpecBuilder.build(..., now: datetime | None = None)`。
- Produces: 可注入时钟的计划命名；验收测试与“商品库已移除、规则集为当前 defaults”一致。

- [x] **Step 1: 写失败测试**：给 `PlanSpecBuilder.build` 传入固定上海时间 `2026-08-07 12:00:00+08:00`，断言任务名创建日期稳定为 `20260807`。
- [x] **Step 2: 验证 RED**：运行 `pytest tests/unit/test_plan_spec_service.py::TestPlanSpecBuilder::test_build_full_plan_spec -q`，确认因 `build()` 不接受 `now` 失败。
- [x] **Step 3: 最小实现**：新增关键字参数 `now: datetime | None = None`，命名时使用 `now or datetime.now(timezone.utc)`；同步移除商品库后的 `product_id` 旧断言，并按 defaults 动态业务事实将规则集数量断言更新为 4。
- [x] **Step 4: 验证 GREEN**：运行三个原失败测试，确认全部通过。

### Task 2: 显式运行模式与真实 Adapter 装配

**Files:**
- Modify: `backend/src/backend/infrastructure/config/settings.py`
- Modify: `backend/src/backend/bootstrap/automation_worker.py`
- Modify: `backend/src/backend/bootstrap/adapters.py`
- Create: `backend/src/backend/infrastructure/browser/worker_browser.py`
- Test: `backend/tests/unit/test_settings.py`
- Test: `backend/tests/unit/test_adapter_factory.py`
- Test: `backend/tests/unit/test_automation_worker.py`

**Interfaces:**
- Produces: `Settings.use_real_adapters: bool`、`build_adapters(settings, page=page)`；Worker 不再传入硬编码 `False`。

- [x] **Step 1: 写失败测试**：设置 `WORKBUDDY_USE_REAL_ADAPTERS=true`，断言 Worker 装配把 `use_real_adapters=True` 传给执行器；没有 Playwright page 时必须抛 `ConfigurationError`，不能静默回退 Mock。
- [x] **Step 2: 验证 RED**：运行对应三个单元测试并确认硬编码 `use_real=False` 导致失败。
- [x] **Step 3: 最小实现**：Settings 增加严格布尔字段；Worker 从设置读取模式，并复用一个持久化 Playwright page 传给 `build_adapters`；Mock 模式继续显式构造 Mock bundle。
- [x] **Step 4: 验证 GREEN**：运行设置、Adapter 工厂和 Worker 装配测试。

### Task 3: 链接准备接入运行链并只消费冻结快照

**Files:**
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Modify: `backend/src/backend/application/services/delivery_scheduler.py`
- Modify: `backend/src/backend/bootstrap/control_server.py`
- Modify: `backend/src/backend/application/services/worker_executor.py`
- Test: `backend/tests/unit/test_task_preparation_service.py`
- Test: `backend/tests/unit/test_delivery_scheduler.py`
- Test: `backend/tests/unit/test_worker_executor.py`

**Interfaces:**
- Produces: `TaskPreparationService.prepare(day, *, dry_run: bool, now: datetime) -> PreparationResult` 与 `prepare_task(...)`；E 时间前零番茄调用，Worker 后续执行仅使用 `task.link_set`。

- [x] **Step 1: 写失败测试**：覆盖番茄到点准备后冻结并回填、剧变直接冻结来源链接、Dry Run 不回填、E 时间前 Tomato Adapter 零调用、Worker 冻结后零二次调用。
- [x] **Step 2: 验证 RED**：确认 `prepare()` 不接受时钟/演练参数，生产 Worker 每次执行都会重新提取。
- [x] **Step 3: 最小实现**：扫描只 upsert 来源数据并创建等待队列；到点领取后调用准备服务，写入 `VALIDATED` 快照；后续执行只读 `link_set`，缺失/无效快照转 `MANUAL_REVIEW`。
- [x] **Step 4: 验证 GREEN**：准备、调度、Worker 执行器及 Phase 10 场景通过。

### Task 4: Dry Run 状态与成功副作用隔离

**Files:**
- Modify: `backend/src/backend/application/services/worker_execution.py`
- Modify: `backend/src/backend/application/services/worker_executor.py`
- Modify: `backend/src/backend/application/services/standard_delivery_service.py`
- Test: `backend/tests/unit/test_worker_execution.py`
- Test: `backend/tests/unit/test_standard_delivery_service.py`
- Test: `backend/tests/integration/test_dry_run_full_scenario.py`

**Interfaces:**
- Produces: `STATUS_DRY_RUN = "DRY_RUN"`、`QueueState.DRY_RUN`、`TaskStatus.DRY_RUN`；该状态为演练终态，但绝不调用 `complete_task()` 或生成成功台账。

- [x] **Step 1: 写失败测试**：安全闸门关闭时断言无成功台账、队列非 `COMPLETED`、任务非 `COMPLETED`、飞书 completion 写入次数为 0。
- [x] **Step 2: 验证 RED**：确认现有 Worker 将 `DELIVERY_DRY_RUN` 转成 `STATUS_COMPLETED` 导致失败。
- [x] **Step 3: 最小实现**：增加明确的 `DRY_RUN` 状态迁移并生成 INFO 事件；WorkerExecutionService 只允许真实 `COMPLETED` 进入完成服务。
- [x] **Step 4: 验证 GREEN**：运行上述单元与集成测试。

### Task 5: 飞书账户端口与条件整块写入

**Files:**
- Modify: `backend/src/backend/domain/ports/adapters.py`
- Create: `backend/src/backend/domain/rules/account_sheet.py`
- Create: `backend/src/backend/application/services/account_assignment_service.py`
- Modify: `backend/src/backend/platforms/feishu/feishu_adapter.py`
- Modify: `backend/src/backend/platforms/mock/mock_feishu.py`
- Modify: `backend/src/backend/application/services/worker_executor.py`
- Test: `backend/tests/unit/test_account_assignment_service.py`
- Test: `backend/tests/unit/test_feishu_adapter.py`
- Test: `backend/tests/integration/test_account_assignment.py`

**Interfaces:**
- Produces: `FeishuAdapter.read_account_rows(...)`、条件整块写入/回读、`append_account_block(...)`；`AccountUsage` 按业务日期持久化 CID 唯一占用；`AccountAssignmentResult(status, accounts, reason)`。

- [x] **Step 1: 写失败测试**：覆盖 IAA 10 行、单价格 IAP 3 行、双价格 IAP 6 行、写前冲突、写后不一致、追加块、同日 CID 唯一占用、Dry Run 零写入。
- [x] **Step 2: 验证 RED**：确认真实账户端口、追加块和持久化占用缺失，Worker 生产路径依赖 Mock 数据。
- [x] **Step 3: 最小实现**：块选择留在 Application；Adapter 只读写飞书。新增写前验证、整块写入、回读、表尾追加、测试户标记和 `account_usage` 唯一约束；生产 Worker 不再使用默认 Mock 账户。
- [x] **Step 4: 验证 GREEN**：账户领域、Feishu Adapter、持久化集成和 Phase 10 测试通过。

### Task 6: 轮询策略与执行中续租

**Files:**
- Modify: `backend/src/backend/infrastructure/config/settings.py`
- Modify: `backend/src/backend/application/services/delivery_flow_service.py`
- Modify: `backend/src/backend/application/services/standard_delivery_service.py`
- Modify: `backend/src/backend/application/services/worker_heartbeat.py`
- Modify: `backend/src/backend/bootstrap/automation_worker.py`
- Test: `backend/tests/unit/test_delivery_flow_service.py`
- Test: `backend/tests/unit/test_worker_heartbeat.py`
- Test: `backend/tests/integration/test_recovery.py`

**Interfaces:**
- Produces: `poll_until_completed(..., poll_interval_seconds=300, timeout_seconds=7200, heartbeat_interval_seconds=30, on_wait: Callable[[], None] | None)`；300 秒查询间隔内每 30 秒调用 `on_wait`，使用独立短事务续租。

- [x] **Step 1: 写失败测试**：用 fake clock/sleeper 验证 0、300、7200 秒边界；每次等待触发续租；租约持续有效时恢复器不得重新入队。
- [x] **Step 2: 验证 RED**：确认现有代码 24 次零间隔轮询且执行中不心跳。
- [x] **Step 3: 最小实现**：从 Settings 注入 300/7200；轮询按截止时间控制；等待回调使用独立 Session 更新 WorkerLease 与 QueueItem.lease_until。
- [x] **Step 4: 验证 GREEN**：运行轮询、心跳和恢复集成测试。

### Task 7: RESULT_UNCERTAIN 对账闸门

**Files:**
- Modify: `backend/src/backend/domain/ports/adapters.py`
- Modify: `backend/src/backend/platforms/delivery_system/delivery_system_adapter.py`
- Modify: `backend/src/backend/application/services/standard_delivery_service.py`
- Modify: `backend/src/backend/application/services/task_control_service.py`
- Test: `backend/tests/unit/test_standard_delivery_service.py`
- Test: `backend/tests/unit/test_task_control_service.py`

**Interfaces:**
- Produces: `DeliverySystemAdapter.find_task_by_idempotency_key(task_name) -> str | None`；执行结果保存 `failure_code="RESULT_UNCERTAIN"`；重试命令要求 `reconciled_absent=True` 或已找到外部任务。

- [x] **Step 1: 写失败测试**：提交超时后查到同名任务则继续轮询；查不到则停在人工处理；未经对账的人工重试被拒绝。
- [x] **Step 2: 验证 RED**：确认异常当前被统一吞掉且重试接口没有对账条件。
- [x] **Step 3: 最小实现**：仅捕获带 `RESULT_UNCERTAIN` code 的异常并执行查询；其他异常维持人工处理；保存结构化失败码，重试前检查。
- [x] **Step 4: 验证 GREEN**：运行标准投放与任务控制测试。

### Task 8: 真实计划填写契约与安全验收

**Files:**
- Modify: `backend/src/backend/domain/plans/plan_spec.py`
- Create: `backend/src/backend/domain/plans/delivery_form_spec.py`
- Modify: `backend/src/backend/platforms/delivery_system/page_objects/plan_submit_page.py`
- Modify: `configs/defaults/delivery_system_selectors.json`
- Test: `backend/tests/unit/test_delivery_form_spec.py`
- Test: `backend/tests/unit/test_delivery_system_adapter.py`
- Test: `backend/tests/integration/test_phase10_full_scenario.py`

**Interfaces:**
- Produces: `DeliveryFormSpec` 明确承载账户、逐 CID 预设、逐 CID 推广内容、素材、标题包、叉乘和任务名；`PlanSubmitPage.fill(form_spec)` 与 `submit(form_spec)` 分离。

- [x] **Step 1: 写失败测试**：使用录制型 fake Page 验证全 CID、逐价格推广内容、全部素材、6 个标题包、一次乱序、固定叉乘规则和主剧不一致拦截。
- [x] **Step 2: 验证 RED**：确认原页面对象只填写首个 CID、首条链接并伪填商品库。
- [x] **Step 3: 最小实现**：新增纯领域 `DeliveryFormSpec`；真实 CID 配置来自采集快照，素材/标题来自剧目级资源文件；Page Object 填写全部数据，缺任何选择器或业务配置时在账户/提交写入前失败。
- [x] **Step 4: 验证 GREEN**：表单领域、页面对象、标准投放和 Phase 10 测试通过。

### Task 9: 全量验证与交付审计

**Files:**
- Modify: `docs/production-validation-runbook.md`
- Modify: `docs/phase10-delivery-summary.md`

- [x] **Step 1: 后端验证**：运行 `pytest -q`，要求 0 failed。
- [x] **Step 2: 前端验证**：运行 `npm test -- --run` 与 `npm run build`，要求退出码 0；记录大包警告但不在本计划做无关重构。
- [x] **Step 3: 静态检查**：运行 `python -m compileall src`、`codegraph sync`、`codegraph status`。
- [x] **Step 4: 业务不变量搜索**：确认生产 Worker 无 `use_real=False`、无 `MOCK_ACCOUNT_ROWS` 默认路径、Worker 无 Tomato 再提取调用、Dry Run 无完成映射。
- [x] **Step 5: 工作区审计**：运行 `git diff --check`、`git status --short`，输出变更清单；不提交，等待用户确认。

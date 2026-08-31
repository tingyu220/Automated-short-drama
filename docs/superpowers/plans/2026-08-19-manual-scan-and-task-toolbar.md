# 手动扫描与任务工具栏优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为剧目调度增加可重复的手动扫描兜底，并将自动搭链接页面的筛选与操作控件整理为稳定、紧凑的工具栏。

**Architecture:** Control Server 复用现有 `DeliveryScheduler.tick()` 用例，新增一个 API 命令入口，使用独立数据库会话执行、提交并返回扫描统计；前端通过 task store 调用该命令并刷新任务/导入记录。页面样式只调整任务页工具栏和导入表，不改变任务状态机或调度规则。

**Tech Stack:** FastAPI、SQLAlchemy、Vue 3、TypeScript、Element Plus、Vitest、Pytest。

## Global Constraints

- Domain 不依赖 FastAPI、数据库或 Playwright。
- Dashboard 不直接写数据库，命令必须经过 API/Application 边界。
- 真实扫描仍按原有每小时后台调度运行，手动扫描只额外执行一次，不创建重复活动队列项。
- 修改前先写失败测试，删除文件前先备份；不提交 Git，等待用户确认。

---

### Task 1: 手动调度扫描命令

**Files:**
- Modify: `backend/src/backend/interfaces/api/routes/tasks.py` 或新建调度命令路由（保持 API 路由边界）
- Modify: `backend/src/backend/bootstrap/control_server.py`（复用真实/模拟 Feishu Adapter 的选择逻辑）
- Test: `backend/tests/unit/test_delivery_scheduler.py`
- Test: `backend/tests/integration/test_task_api.py`

**Interfaces:**
- Produces `POST /api/tasks/scan`，返回 `{day, created_tasks, updated_tasks, enqueued, skipped}`。
- 命令使用当前上海日期，复用 `DeliveryScheduler.tick(datetime.now(timezone.utc))`，完成后提交独立 Session。

- [ ] Step 1: 为 API 命令写失败测试，断言成功返回扫描统计、调用一次 `tick`，异常时返回可读错误且事务回滚。
- [ ] Step 2: 运行 `python -m pytest backend/tests/integration/test_task_api.py -q`，确认新命令测试先失败。
- [ ] Step 3: 实现最小命令入口，复用 Control Server 的 Adapter 选择策略与 `DeliveryScheduler`，不复制扫描业务逻辑。
- [ ] Step 4: 运行调度与 API 测试，确认命令成功、失败回滚和重复扫描幂等。

### Task 2: 前端手动扫描与状态语义

**Files:**
- Modify: `dashboard/src/app/stores/task.ts`
- Modify: `dashboard/src/pages/tasks/index.vue`
- Modify: `dashboard/src/widgets/imported-drama-table/ImportedDramaTable.vue`
- Test: `dashboard/tests/unit/stores.spec.ts`
- Test: `dashboard/tests/unit/imported-drama-table.spec.ts`

**Interfaces:**
- Produces `taskStore.scanTasks()`，调用 `POST /api/tasks/scan` 并返回统计结果。
- “等待扫描”显示为“待关联任务”，表示导入记录尚未匹配本地 `task_id`；带原生 `title` 说明，不改变选中规则。

- [ ] Step 1: 写 Store 调用和状态文案失败测试，断言请求方法、成功统计和“待关联任务”文本。
- [ ] Step 2: 运行对应 Vitest 测试，确认实现前失败。
- [ ] Step 3: 增加“立即扫描”按钮，调用扫描后刷新任务、队列和导入记录，并提示创建/更新/入队数量。
- [ ] Step 4: 运行前端单测，确认按钮 loading、错误提示和状态文案通过。

### Task 3: 任务筛选工具栏布局

**Files:**
- Modify: `dashboard/src/pages/tasks/index.vue`
- Modify: `dashboard/tests/unit/task-table.spec.ts`（若需补充页面级渲染契约）

**Interfaces:**
- 桌面端使用两列 CSS Grid：左侧筛选条件，右侧操作；中等宽度操作区换到下一行但左对齐；小屏幕控件全宽堆叠。
- 不改变已有筛选字段、按钮行为、任务表数据和分页。

- [ ] Step 1: 增加页面级布局断言或快照契约，锁定 `.tasks-filter`、`.tasks-filter__criteria`、`.tasks-filter__actions` 的结构。
- [ ] Step 2: 运行前端测试确认布局契约先失败或缺少新按钮。
- [ ] Step 3: 用 CSS Grid 与明确的 `minmax`/断点替换当前可变 Flex 换行，统一控件高度和间距。
- [ ] Step 4: 运行前端测试与构建，检查桌面和窄屏无溢出。

### Task 4: 全量验证与运行验证

**Files:**
- Modify: `docs/production-validation-runbook.md`（记录手动扫描入口和状态语义）

- [ ] Step 1: 运行后端相关测试、前端 `npm test -- --run`、`npm run build`、`python -m compileall -q src`。
- [ ] Step 2: 启动或重载 Control Server，调用手动扫描接口，确认返回统计且导入表状态刷新。
- [ ] Step 3: 用桌面与窄屏截图检查工具栏对齐、按钮可见性、表格横向滚动和状态标签。
- [ ] Step 4: 运行 `git diff --check` 与 `git status --short`，列出变更，不提交 Git。

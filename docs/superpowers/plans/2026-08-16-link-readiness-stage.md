# 链接就绪阶段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 剧目上线时间到达后，幂等获取番茄链接，在投放系统创建或复用剧目与推广内容，并按用户指定终点停在“链接已提取”或“链接已就绪”。

**Architecture:** 新增独立 `LinkReadinessService` 编排四个可恢复阶段，阶段状态和产物写入任务与 StepRun；番茄 Page Object 负责“先搜索查看、缺失才创建”，投放系统继续通过现有 Adapter 幂等创建。Worker 默认只执行链接准备，不再进入账户、素材或计划服务。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、Playwright、pytest、Vue 3、TypeScript、Pinia、Element Plus、Vitest。

## Global Constraints

- 番茄链接只能在剧目上线时间到达后提取。
- 已存在链接必须搜索并点击查看提取，禁止重复创建。
- 投放系统必须先创建或复用剧目，再创建或复用推广内容。
- 默认运行终点为 `LINK_READY`，可手动选择 `LINK_EXTRACTION`。
- 本期禁止账户分配、素材处理、计划生成、计划提交、状态轮询和飞书 M=1。
- 单 Worker、单浏览器、单标签页串行执行。
- 不提交 Git；完成后由用户确认，Commit Message 使用中文。

---

### Task 1: 阶段状态与持久化契约

**Files:**
- Create: `backend/alembic/versions/20260816_0012_link_readiness_stage.py`
- Create: `backend/src/backend/domain/workflow/link_stage.py`
- Create: `backend/src/backend/infrastructure/database/repositories/workflow_repository.py`
- Modify: `backend/src/backend/domain/tasks/drama_task.py`
- Modify: `backend/src/backend/infrastructure/database/models/task.py`
- Modify: `backend/src/backend/infrastructure/database/repositories/task_repository.py`
- Modify: `backend/src/backend/domain/ports/repositories.py`
- Test: `backend/tests/unit/test_link_stage.py`
- Test: `backend/tests/unit/test_workflow_repository.py`
- Test: `backend/tests/unit/test_task_repository.py`

**Interfaces:**
- Produces: `LinkStage`, `RunTarget`, `DramaTask.current_stage`, `DramaTask.target_stage`, `DramaTask.delivery_drama_id`, `DramaTask.promotion_configs`。
- Produces: `SqlAlchemyWorkflowRepository.start_step(task_id, step_name)`、`finish_step(step, result)`、`fail_step(step, code, message)`、`list_task_steps(task_id)`。

- [ ] **Step 1: Write the failing tests**

```python
def test_run_target_orders_link_extraction_before_link_ready():
    assert RunTarget.reaches("LINK_READY", LinkStage.PROMOTION_CONFIG)
    assert not RunTarget.reaches("LINK_EXTRACTION", LinkStage.DELIVERY_DRAMA)

def test_task_repository_round_trips_link_readiness_fields(session):
    task = make_task(
        current_stage="DELIVERY_DRAMA",
        target_stage="LINK_READY",
        delivery_drama_id="dd-1",
        promotion_configs={"IAA": "iaa-番茄-剧A"},
    )
    repo = SqlAlchemyTaskRepository(session)
    repo.add(task)
    assert repo.get(task.id).promotion_configs == {"IAA": "iaa-番茄-剧A"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_link_stage.py backend/tests/unit/test_workflow_repository.py backend/tests/unit/test_task_repository.py -q`
Expected: FAIL because stage types, fields and repository do not exist.

- [ ] **Step 3: Implement the minimal stage model and migration**

```python
class LinkStage:
    WAITING_AVAILABLE_TIME = "WAITING_AVAILABLE_TIME"
    LINK_EXTRACTION = "LINK_EXTRACTION"
    DELIVERY_DRAMA = "DELIVERY_DRAMA"
    PROMOTION_CONFIG = "PROMOTION_CONFIG"
    LINK_READY = "LINK_READY"

class RunTarget:
    LINK_EXTRACTION = LinkStage.LINK_EXTRACTION
    LINK_READY = LinkStage.LINK_READY
```

Add nullable/default-safe task columns: `current_stage`, `target_stage`, `delivery_drama_id`, `promotion_configs_json`. Implement StepRun persistence using the existing `workflow_run` and `step_run` tables; JSON must be serialized with `ensure_ascii=False`.

- [ ] **Step 4: Run tests and migration check**

Run: `pytest backend/tests/unit/test_link_stage.py backend/tests/unit/test_workflow_repository.py backend/tests/unit/test_task_repository.py -q`
Expected: PASS.

Run: `python -m backend.infrastructure.database.migrations`
Expected: migration reaches revision `20260816_0012`.

- [ ] **Step 5: Review Task 1 changes**

Run: `git diff --check`
Expected: no whitespace errors. Do not commit until the user confirms.

### Task 2: 番茄链接先查后建

**Files:**
- Create: `backend/src/backend/platforms/tomato/page_objects/promotion_link_list.py`
- Modify: `backend/src/backend/platforms/tomato/page_objects/free_entry.py`
- Modify: `backend/src/backend/platforms/tomato/page_objects/paid_entry.py`
- Modify: `backend/src/backend/platforms/tomato/tomato_adapter.py`
- Modify: `configs/defaults/tomato_selectors.json`
- Test: `backend/tests/unit/test_tomato_adapter.py`
- Test: `backend/tests/unit/test_tomato_promotion_link_list.py`

**Interfaces:**
- Produces: `PromotionLinkListPage.find_existing(drama_name, identity) -> str | None`。
- Keeps: `TomatoAdapter.extract_iaa_link(...)` and `generate_iap_link(...)`; their behavior becomes resolve-existing-or-create.

- [ ] **Step 1: Write failing reuse and ambiguity tests**

```python
def test_existing_iaa_link_is_viewed_without_generate_click():
    page = promotion_page(rows=[("剧A", "第2集", "aweme://existing")])
    link = adapter(page).extract_iaa_link("剧A", NOW, 80, 2)
    assert link.promotion_url == "aweme://existing"
    assert generate_button(page).calls == []

def test_existing_iap_template_link_is_viewed_without_create():
    link = adapter(page_with_existing("剧A", "模板9.9")).generate_iap_link(
        "剧A", NOW, template("模板9.9")
    )
    assert link.promotion_url == "aweme://existing-9.9"

def test_multiple_exact_links_raise_manual_review_error():
    with pytest.raises(ExternalAdapterError) as exc:
        list_page(two_exact_rows()).find_existing("剧A", "第2集")
    assert exc.value.code == "TOMATO_LINK_AMBIGUOUS"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_tomato_adapter.py backend/tests/unit/test_tomato_promotion_link_list.py -q`
Expected: FAIL because current code always clicks generate and has no promotion-link lookup.

- [ ] **Step 3: Implement search/view/create flow**

```python
existing = PromotionLinkListPage(page, selectors).find_existing(
    drama_name,
    f"第{selected_episode}集",
)
if existing:
    return existing
free_entry.generate_link(selected_episode)
return free_entry.read_link()
```

The IAP identity is `template.title or template.template_id`. Add selectors for promotion list URL, search input/button, row, row name, row identity, view button and detail link. Zero match returns `None`; exactly one match clicks view and reads the URL; multiple exact matches raise `TOMATO_LINK_AMBIGUOUS`.

- [ ] **Step 4: Run focused tests**

Run: `pytest backend/tests/unit/test_tomato_adapter.py backend/tests/unit/test_tomato_promotion_link_list.py backend/tests/unit/test_tomato_extraction_service.py -q`
Expected: PASS.

- [ ] **Step 5: Review Task 2 changes**

Run: `git diff --check`
Expected: no whitespace errors. Do not commit until the user confirms.

### Task 3: 链接就绪编排服务

**Files:**
- Create: `backend/src/backend/application/services/link_readiness_service.py`
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Modify: `backend/src/backend/application/services/delivery_flow_service.py`
- Test: `backend/tests/unit/test_link_readiness_service.py`
- Test: `backend/tests/integration/test_link_readiness_flow.py`

**Interfaces:**
- Consumes: `TaskPreparationService.prepare_task(...)`, `DeliveryFlowService.ensure_drama_asset(...)`, `ensure_promotion_config(...)`, workflow repository from Task 1.
- Produces: `LinkReadinessService.execute(task, target_stage, dry_run, now) -> LinkReadinessOutcome`.

- [ ] **Step 1: Write failing stage-boundary tests**

```python
def test_link_extraction_target_stops_before_delivery():
    outcome = service.execute(task, "LINK_EXTRACTION", dry_run=False, now=NOW)
    assert outcome.status == "LINK_EXTRACTED"
    assert delivery.calls == []

def test_link_ready_orders_asset_before_promotion_configs():
    outcome = service.execute(task, "LINK_READY", dry_run=False, now=NOW)
    assert outcome.status == "LINK_READY"
    assert [call.name for call in delivery.calls] == [
        "find_or_create_drama_asset",
        "ensure_promotion_config",
        "ensure_promotion_config",
        "ensure_promotion_config",
    ]

def test_resume_skips_completed_link_stage():
    task.link_status = "VALIDATED"
    task.link_set = {"IAA": "aweme://iaa"}
    service.execute(task, "LINK_READY", dry_run=False, now=NOW)
    assert tomato.calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_link_readiness_service.py backend/tests/integration/test_link_readiness_flow.py -q`
Expected: FAIL because the independent orchestrator does not exist.

- [ ] **Step 3: Implement the stage executor**

```python
def execute(self, task, target_stage, *, dry_run, now):
    self._require_available(task, now)
    task = self._ensure_links(task, dry_run=dry_run, now=now)
    if target_stage == RunTarget.LINK_EXTRACTION:
        return LinkReadinessOutcome("LINK_EXTRACTED", task)
    asset = self._ensure_delivery_drama(task)
    configs = self._ensure_promotion_configs(task, asset)
    return LinkReadinessOutcome("LINK_READY", task, asset, configs)
```

Persist a StepRun around each external stage. A completed stage with stored output is reused. `RESULT_UNCERTAIN`, drama mismatch and ambiguous Tomato links end in `MANUAL_REVIEW`; no later stage runs.

- [ ] **Step 4: Run focused tests**

Run: `pytest backend/tests/unit/test_link_readiness_service.py backend/tests/integration/test_link_readiness_flow.py backend/tests/unit/test_task_preparation_service.py backend/tests/unit/test_delivery_flow_service.py -q`
Expected: PASS.

- [ ] **Step 5: Review Task 3 changes**

Run: `git diff --check`
Expected: no whitespace errors. Do not commit until the user confirms.

### Task 4: Worker 与 API 运行终点

**Files:**
- Modify: `backend/src/backend/application/services/worker_executor.py`
- Modify: `backend/src/backend/application/services/worker_execution.py`
- Modify: `backend/src/backend/bootstrap/automation_worker.py`
- Modify: `backend/src/backend/interfaces/api/routes/tasks.py`
- Modify: `backend/src/backend/interfaces/api/schemas.py`
- Test: `backend/tests/unit/test_worker_executor.py`
- Test: `backend/tests/unit/test_worker_execution.py`
- Test: `backend/tests/integration/test_tasks_api.py`

**Interfaces:**
- Produces: `POST /api/tasks/{task_id}/enqueue` body `{ "target_stage": "LINK_EXTRACTION" | "LINK_READY" }`。
- Produces: task detail fields `current_stage`, `target_stage`, `link_set`, `delivery_drama_id`, `promotion_configs`, `steps`。

- [ ] **Step 1: Write failing worker and API tests**

```python
def test_real_worker_stops_at_link_ready_without_account_or_plan_calls():
    outcome = executor(task, queue_item)
    assert outcome.status == "LINK_READY"
    assert delivery.submit_calls == []
    assert feishu.account_writes == []
    assert feishu.completion_writes == []

def test_enqueue_accepts_link_extraction_target(client, task):
    response = client.post(
        f"/api/tasks/{task.id}/enqueue",
        json={"target_stage": "LINK_EXTRACTION"},
    )
    assert response.status_code == 201
    assert client.get(f"/api/tasks/{task.id}").json()["target_stage"] == "LINK_EXTRACTION"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_worker_executor.py backend/tests/unit/test_worker_execution.py backend/tests/integration/test_tasks_api.py -q`
Expected: FAIL because Worker always continues into the full delivery plan and API has no target stage.

- [ ] **Step 3: Switch Worker to link-readiness execution**

Default scheduled and manual enqueue target to `LINK_READY`. Map link terminal outcomes to completed queue state while preserving task status `LINK_EXTRACTED` or `LINK_READY`; do not create completion ledger and do not call `complete_task()` for these outcomes.

```python
if outcome.status in {"LINK_EXTRACTED", "LINK_READY"}:
    item.state = QueueState.COMPLETED
    task.status = outcome.status
    self._queue_repo.update(item)
    self._task_repo.update(task)
```

- [ ] **Step 4: Run focused backend tests**

Run: `pytest backend/tests/unit/test_worker_executor.py backend/tests/unit/test_worker_execution.py backend/tests/integration/test_tasks_api.py -q`
Expected: PASS.

- [ ] **Step 5: Review Task 4 changes**

Run: `git diff --check`
Expected: no whitespace errors. Do not commit until the user confirms.

### Task 5: Dashboard 阶段控制与产物展示

**Files:**
- Modify: `dashboard/src/entities/task/types.ts`
- Modify: `dashboard/src/app/stores/task.ts`
- Modify: `dashboard/src/pages/tasks/index.vue`
- Modify: `dashboard/src/features/task-detail/TaskDetailDrawer.vue`
- Test: `dashboard/tests/unit/task-stage-control.spec.ts`
- Test: `dashboard/tests/unit/task-detail.spec.ts`

**Interfaces:**
- Consumes: Task 4 task detail and enqueue API.
- Produces: manual run target selector and stage/output display.

- [ ] **Step 1: Write failing component tests**

```ts
it("can run only to link extraction", async () => {
  await wrapper.get('[aria-label="运行终点"]').setValue("LINK_EXTRACTION")
  await wrapper.get('[aria-label="运行任务"]').trigger("click")
  expect(enqueueTask).toHaveBeenCalledWith("task-1", "LINK_EXTRACTION")
})

it("shows link-ready outputs", () => {
  expect(wrapper.text()).toContain("投放剧目 ID")
  expect(wrapper.text()).toContain("dd-1")
  expect(wrapper.text()).toContain("iaa-番茄-剧A")
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- task-stage-control.spec.ts task-detail.spec.ts`
Expected: FAIL because target selection and readiness outputs are absent.

- [ ] **Step 3: Implement the minimal operational UI**

Use an Element Plus select with two options: “仅提取链接” and “搭建链接完成”. Keep the default as `LINK_READY`. Show stage timeline and outputs in the existing task drawer; reuse current page density and status colors.

```ts
async function enqueueTask(id: string, targetStage = "LINK_READY") {
  await apiPost(`/tasks/${id}/enqueue`, { target_stage: targetStage })
}
```

- [ ] **Step 4: Run dashboard tests and build**

Run: `npm test -- task-stage-control.spec.ts task-detail.spec.ts`
Expected: PASS.

Run: `npm run build`
Expected: exit code 0.

- [ ] **Step 5: Review Task 5 changes**

Run: `git diff --check`
Expected: no whitespace errors. Do not commit until the user confirms.

### Task 6: 全量验证与文档同步

**Files:**
- Modify: `docs/workflows/full-workflow.md`
- Modify: `docs/rules/business-rules.md`
- Verify: `backend/tests`
- Verify: `dashboard/tests/unit`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified link-readiness release candidate.

- [ ] **Step 1: Update workflow documentation**

Document the two supported targets and make `LINK_READY` the current production terminal. State explicitly that later plan phases remain disabled.

- [ ] **Step 2: Run backend tests**

Run: `pytest backend/tests -q`
Expected: PASS.

- [ ] **Step 3: Run dashboard tests**

Run: `npm test`
Expected: PASS.

- [ ] **Step 4: Run production build**

Run: `npm run build`
Expected: exit code 0.

- [ ] **Step 5: Inspect final worktree**

Run: `git diff --check`

Run: `git status --short`

Expected: only intended implementation files plus pre-existing user changes; no commit is created before user confirmation.

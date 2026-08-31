# 番茄时间容差与人工确认剧目 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 番茄时间与飞书时间小幅偏差时自动安全匹配，人工确认候选后可以继续执行而不重复触发原始匹配失败。

**Architecture:** 领域匹配器保留完全剧名匹配并引入 ±5 分钟唯一窗口。人工确认使用独立的候选确认值对象，持久化定位键和番茄分钟；番茄选择页收到确认后只查找该定位并核验剧名和时间未变化。API 从最近的失败事件读取候选证据，确认后重新入队；任务详情提供候选选择入口。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy/Alembic、Playwright Page Object、Vue 3、Element Plus、pytest、Vitest。

## Global Constraints

- 剧名必须标准化后完全相等，禁止模糊匹配。
- 自动匹配仅允许上海时区分钟差绝对值不大于 5 且唯一的候选。
- 超出窗口或多个候选不得自动选择，仍进入 `DRAMA_MISMATCH`。
- 人工确认只允许确认失败事件中同名的候选，并保留定位键和番茄分钟。
- 已确认候选在后续执行中必须仍存在、剧名和分钟均未变化，否则再次转人工。
- 不能以普通重试绕过 `DRAMA_MISMATCH` 的人工确认。
- 不自动重跑已失败的真实任务；确认后由用户操作重新入队。

---

### Task 1: 时间容差唯一匹配

**Files:**
- Modify: `backend/src/backend/domain/rules/drama_match.py`
- Modify: `backend/tests/unit/test_drama_match.py`
- Modify: `docs/rules/business-rules.md`

**Interfaces:**
- Produces: `match_unique_drama(expected_name: str, expected_time: datetime, candidates: list[DramaCandidate]) -> DramaCandidate`，失败详情包含 `time_difference_minutes`。

- [ ] **Step 1: 写失败测试**

```python
def test_unique_same_name_candidate_within_five_minutes_matches() -> None:
    expected = datetime(2026, 8, 19, 0, 55, tzinfo=SHANGHAI_TZ)
    candidate = _candidate(
        "剧A", datetime(2026, 8, 19, 0, 53, tzinfo=SHANGHAI_TZ), "/detail/a"
    )
    assert match_unique_drama("剧A", expected, [candidate]) == candidate

def test_same_name_candidate_outside_five_minutes_is_rejected() -> None:
    expected = datetime(2026, 8, 19, 0, 55, tzinfo=SHANGHAI_TZ)
    candidate = _candidate(
        "剧A", datetime(2026, 8, 19, 0, 49, tzinfo=SHANGHAI_TZ), "/detail/a"
    )
    with pytest.raises(DramaMismatchError):
        match_unique_drama("剧A", expected, [candidate])
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/unit/test_drama_match.py -q`

Expected: 新增的 2 分钟偏差断言失败。

- [ ] **Step 3: 实现最小规则**

```python
MATCH_TOLERANCE_MINUTES = 5

def _minute_difference(left: datetime, right: datetime) -> int:
    return int(abs((left - right).total_seconds()) // 60)

matches = [
    item for item in candidates
    if normalize_drama_name(item.drama_name) == normalized_name
    and _minute_difference(shanghai_minute(item.available_time), expected_minute)
    <= MATCH_TOLERANCE_MINUTES
]
```

为失败详情中的每个候选增加 `time_difference_minutes`；业务规则替换“分钟一致”为“5 分钟内唯一”。

- [ ] **Step 4: 运行领域测试**

Run: `python -m pytest backend/tests/unit/test_drama_match.py -q`

Expected: 现有精确匹配、超窗拒绝、窗口多候选拒绝和时区校验均通过。

---

### Task 2: 已确认候选的持久化与数据库映射

**Files:**
- Create: `backend/src/backend/domain/rules/confirmed_drama_match.py`
- Create: `backend/alembic/versions/20260819_0016_confirmed_drama_match.py`
- Modify: `backend/src/backend/domain/tasks/drama_task.py`
- Modify: `backend/src/backend/infrastructure/database/models/task.py`
- Modify: `backend/src/backend/infrastructure/database/repositories/task_repository.py`
- Modify: `backend/tests/unit/test_task_preparation_service.py`
- Modify: `backend/tests/unit/test_migrations.py`

**Interfaces:**
- Produces: `ConfirmedDramaMatch(locator_key: str, available_minute: datetime, confirmed_at: datetime)`。
- Consumes: `DramaTask.confirmed_drama_match: ConfirmedDramaMatch | None`。

- [ ] **Step 1: 写失败测试**

```python
def test_task_repository_round_trips_confirmed_drama_match(session) -> None:
    task = DramaTask(
        id="task-1", drama_name="剧A", platform="TOMATO",
        available_time=datetime(2026, 8, 19, tzinfo=timezone.utc),
        confirmed_drama_match=ConfirmedDramaMatch(
            locator_key="/detail/a",
            available_minute=datetime(2026, 8, 19, 0, 53, tzinfo=SHANGHAI_TZ),
            confirmed_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        ),
    )
    repo.add(task)
    assert repo.get("task-1").confirmed_drama_match.locator_key == "/detail/a"
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/unit/test_task_preparation_service.py -q`

Expected: `DramaTask` 不接受 `confirmed_drama_match`。

- [ ] **Step 3: 实现领域值对象、迁移和仓储转换**

```python
@dataclass(frozen=True)
class ConfirmedDramaMatch:
    locator_key: str
    available_minute: datetime
    confirmed_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "locator_key": self.locator_key,
            "available_minute": self.available_minute.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, str]) -> "ConfirmedDramaMatch | None":
        if not raw.get("locator_key"):
            return None
        return cls(
            locator_key=raw["locator_key"],
            available_minute=datetime.fromisoformat(raw["available_minute"]),
            confirmed_at=datetime.fromisoformat(raw["confirmed_at"]),
        )
```

新增 `drama_task.confirmed_drama_match_json TEXT NOT NULL DEFAULT '{}'`；仓储只序列化该值对象的三个字段，坏数据读取为空确认而不是猜测。

- [ ] **Step 4: 运行迁移和仓储测试**

Run: `python -m pytest backend/tests/unit/test_migrations.py backend/tests/unit/test_task_preparation_service.py -q`

Expected: 新数据库可迁移，确认值对象跨 ORM 往返不丢失时区。

---

### Task 3: 番茄页面按人工确认候选复核

**Files:**
- Modify: `backend/src/backend/domain/ports/adapters.py`
- Modify: `backend/src/backend/application/services/tomato_extraction_service.py`
- Modify: `backend/src/backend/platforms/tomato/page_objects/drama_selection.py`
- Modify: `backend/src/backend/platforms/tomato/tomato_adapter.py`
- Modify: `backend/src/backend/platforms/mock/mock_tomato.py`
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Modify: `backend/tests/unit/test_tomato_adapter.py`
- Modify: `backend/tests/unit/test_mock_adapters.py`
- Modify: `backend/tests/unit/test_tomato_extraction_service.py`
- Modify: `backend/tests/unit/test_task_preparation_service.py`

**Interfaces:**
- Consumes: `ConfirmedDramaMatch | None`，作为 Tomato Adapter 所有读取/生成操作的可选最后参数。
- Produces: `DramaSelectionPage.select_and_verify(drama_name: str, available_time: datetime, confirmed_match: ConfirmedDramaMatch | None = None)`；确认候选失效时抛 `DramaMismatchError(reason="CONFIRMED_CANDIDATE_CHANGED")`。

- [ ] **Step 1: 写失败测试**

```python
def test_confirmed_locator_bypasses_window_but_verifies_same_candidate() -> None:
    page = FakePage()
    configure_drama_candidates(page, [["剧A", "2026-08-19 00:40", "/detail/a"]])
    confirmation = ConfirmedDramaMatch("/detail/a", datetime(2026, 8, 19, 0, 40, tzinfo=SHANGHAI_TZ), NOW)
    make_adapter(page, dry_run=False).extract_iaa_link("剧A", TARGET_TIME, 1, 1, confirmation)
    assert page.locators[f'{SELECTORS["detail_link"]}[href="/detail/a"]'].calls == [("click", (), {})]

def test_confirmed_locator_with_changed_time_is_rejected() -> None:
    # 确认时为 00:40，当前页面改为 00:41。
    page = FakePage()
    configure_drama_candidates(page, [["剧A", "2026-08-19 00:41", "/detail/a"]])
    confirmation = ConfirmedDramaMatch("/detail/a", datetime(2026, 8, 19, 0, 40, tzinfo=SHANGHAI_TZ), NOW)
    adapter = make_adapter(page, dry_run=False)
    with pytest.raises(DramaMismatchError, match="已确认候选已变化"):
        adapter.extract_iaa_link("剧A", TARGET_TIME, 1, 1, confirmation)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/unit/test_tomato_adapter.py -q`

Expected: Adapter 方法不接受确认候选参数。

- [ ] **Step 3: 实现固定候选复核路径**

```python
def _match_confirmed(
    expected_name: str,
    confirmation: ConfirmedDramaMatch,
    candidates: list[DramaCandidate],
) -> DramaCandidate:
    matches = [item for item in candidates if item.locator_key == confirmation.locator_key]
    if len(matches) != 1 or normalize_drama_name(matches[0].drama_name) != normalize_drama_name(expected_name) or shanghai_minute(matches[0].available_time) != confirmation.available_minute:
        raise DramaMismatchError("已确认候选已变化", details={"reason": "CONFIRMED_CANDIDATE_CHANGED"})
    return matches[0]
```

`TomatoAdapter` 协议、真实 Adapter、Mock Adapter 与 `scan_iap()`/`extract_iaa()` 都接收 `confirmed_match: ConfirmedDramaMatch | None = None`，并完整传递该参数。`TaskPreparationService._resolve_links()` 传入 `task.confirmed_drama_match`；成功提取后清除该确认，避免未来无关重跑复用旧确认。

- [ ] **Step 4: 运行链接提取测试**

Run: `python -m pytest backend/tests/unit/test_tomato_adapter.py backend/tests/unit/test_task_preparation_service.py backend/tests/unit/test_tomato_extraction_service.py -q`

Expected: 自动匹配和人工确认路径均通过；候选改变时不点击生成按钮。

---

### Task 4: 确认 API、普通重试保护与任务详情候选证据

**Files:**
- Modify: `backend/src/backend/interfaces/api/routes/tasks.py`
- Modify: `backend/src/backend/interfaces/api/schemas.py`
- Modify: `backend/tests/integration/test_task_api.py`

**Interfaces:**
- Produces: `POST /api/tasks/{task_id}/confirm-drama-match`，Body 为 `DramaMatchConfirmationBody(locator_key: str)`。
- Produces: `TaskDetail.drama_match_candidates` 与 `TaskDetail.confirmed_drama_match`。

- [ ] **Step 1: 写失败测试**

```python
def test_confirm_drama_match_saves_candidate_and_requeues(client, session_factory):
    # 创建 MANUAL_REVIEW/DRAMA_MISMATCH 队列项和带 candidates 的执行事件。
    response = client.post(f"/api/tasks/{task_id}/confirm-drama-match", json={"locator_key": "/detail/a"})
    assert response.status_code == 200
    assert response.json()["state"] == QueueState.QUEUED
    assert client.get(f"/api/tasks/{task_id}").json()["confirmed_drama_match"]["locator_key"] == "/detail/a"

def test_enqueue_rejects_unconfirmed_drama_mismatch(client, session_factory):
    response = client.post(f"/api/tasks/{task_id}/enqueue")
    assert response.status_code == 409
    assert response.json()["code"] == "CONFLICT"
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest backend/tests/integration/test_task_api.py -q`

Expected: 确认接口 404，普通入队错误地返回 200。

- [ ] **Step 3: 实现 API 校验与队列状态转换**

读取最新 `DRAMA_MISMATCH` 事件的 `context_json.candidates`，仅接受其中剧名标准化后等于任务剧名的 `locator_key`；将候选分钟解析为上海时区后持久化 `ConfirmedDramaMatch`。只有 `MANUAL_REVIEW/DRAMA_MISMATCH` 队列项可确认，确认后复用 `retry_task()` 进入 `QUEUED`。`/enqueue` 对未确认的 `DRAMA_MISMATCH` 返回带处理提示的 `ConflictError`。

- [ ] **Step 4: 运行 API 测试**

Run: `python -m pytest backend/tests/integration/test_task_api.py backend/tests/integration/test_link_readiness_flow.py -q`

Expected: 候选证据可读取，确认后可入队，普通继续不能绕过，链接准备阶段状态不回退。

---

### Task 5: 任务详情的候选确认操作

**Files:**
- Create: `dashboard/src/features/drama-match-confirmation/DramaMatchConfirmationPanel.vue`
- Modify: `dashboard/src/app/stores/task.ts`
- Modify: `dashboard/src/features/task-detail/TaskDetailDrawer.vue`
- Modify: `dashboard/src/pages/tasks/index.vue`
- Modify: `dashboard/tests/unit/task-detail.spec.ts`
- Modify: `dashboard/tests/unit/stores.spec.ts`

**Interfaces:**
- Consumes: `TaskDetail.drama_match_candidates`、`TaskDetail.confirmed_drama_match`、`confirmDramaMatch(taskId, locatorKey)`。
- Produces: 一个候选行对应一个“确认并继续”命令；无候选时只显示失败证据，不显示确认按钮。

- [ ] **Step 1: 写失败测试**

```ts
it("匹配失败时展示候选，并只在确认后调用确认接口", async () => {
  const wrapper = mount(TaskDetailDrawer, { props: { open: true, task: mismatchTask } })
  await wrapper.get('[data-testid="confirm-drama-match-/detail/a"]').trigger("click")
  expect(wrapper.emitted("confirm-drama-match")?.[0]).toEqual([["/detail/a"]])
})

it("confirmDramaMatch 调用专用确认接口", async () => {
  await store.confirmDramaMatch("task-1", "/detail/a")
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/tasks/task-1/confirm-drama-match",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ locator_key: "/detail/a" }) })
  )
})
```

- [ ] **Step 2: 运行失败测试**

Run: `npm test -- --run tests/unit/task-detail.spec.ts tests/unit/stores.spec.ts`

Expected: 缺少确认面板和 Store 方法。

- [ ] **Step 3: 实现确认面板与页面编排**

确认面板用紧凑表格显示番茄时间、与飞书的分钟差和候选定位；只有 `failure_code === "DRAMA_MISMATCH"` 且存在候选时渲染。任务页收到确认事件后调用 Store、显示成功消息、刷新列表和详情。任务表的“继续”遇到未确认的 `DRAMA_MISMATCH` 时打开任务详情并提示在候选表确认，而不调用 `/enqueue`。

- [ ] **Step 4: 运行前端验证**

Run: `npm test -- --run tests/unit/task-detail.spec.ts tests/unit/stores.spec.ts && npm run build`

Expected: 单元测试通过，生产构建成功。

---

### Task 6: 全链路验证与运行生效

**Files:**
- Modify: `docs/rules/business-rules.md`
- Modify: `docs/workflows/delivery-launch-flow.md`

- [ ] **Step 1: 运行后端回归**

Run: `python -m pytest backend/tests/unit/test_drama_match.py backend/tests/unit/test_tomato_adapter.py backend/tests/unit/test_task_preparation_service.py backend/tests/integration/test_task_api.py backend/tests/integration/test_link_readiness_flow.py -q`

Expected: 所有测试通过。

- [ ] **Step 2: 运行前端回归和构建**

Run: `cd dashboard; npm test -- --run; npm run build`

Expected: 单元测试和构建均成功。

- [ ] **Step 3: 静态检查与迁移检查**

Run: `git diff --check; python -m backend.infrastructure.database.migrations; git status --short`

Expected: 无空白错误，迁移成功，列出本功能涉及的文件。

- [ ] **Step 4: 重启运行服务并检查**

Run: 重启 Control Server 与 Worker，随后请求 `GET /healthz`。

Expected: `worker_heartbeat=true`、`environment=REAL`、`worker_environment=REAL`。

- [ ] **Step 5: 提交前确认**

不提交 Git；向用户列出改动和验证结果，并等待明确的提交确认。

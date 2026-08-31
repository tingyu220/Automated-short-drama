# 同名剧分钟级防误选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 番茄 IAA/IAP 链接生成前，使用“标准化剧名 + 上海时区分钟”在列表页唯一匹配并在详情页复核，任何不确定结果均停止并转人工。

**Architecture:** Domain 提供纯匹配器和候选 DTO；Application 显式把任务时间传入 Tomato 端口；Tomato Adapter 复用一个两阶段选择器，Page Object 只读取页面字段和执行定位。匹配失败使用 `DRAMA_MISMATCH` 贯穿任务状态与执行事件，不允许首条、最近时间或模糊剧名兜底。

**Tech Stack:** Python 3.12、dataclasses、Playwright Page Object、pytest、JSON selector configuration

## Global Constraints

- 匹配键固定为 `标准化剧名 + 上海时区 YYYY-MM-DD HH:mm`，秒和微秒忽略。
- 零匹配、多匹配、时间无法解析、详情复核失败均为 `DRAMA_MISMATCH`。
- 禁止选择第一条、最近时间、页面顺序或模糊剧名作为兜底。
- IAA 与 IAP 必须复用同一个匹配器和两阶段选择器。
- 详情复核成功前，生成链接按钮调用次数必须为 0。
- 不改变现有选集、IAP 价格、链接回填、账户和投放规则。
- 本计划不提交 Git；完成验证后等待用户确认提交范围。

---

### Task 1: 领域候选模型与分钟级唯一匹配器

**Files:**
- Create: `backend/src/backend/domain/rules/drama_match.py`
- Modify: `backend/src/backend/domain/errors/domain_error.py`
- Test: `backend/tests/unit/test_drama_match.py`

**Interfaces:**
- Consumes: `backend.domain.common.timezones.SHANGHAI_TZ` 与 aware `datetime`。
- Produces: `DramaCandidate(drama_name, available_time, locator_key, raw_time, page_order)`、`match_unique_drama(expected_name, expected_time, candidates) -> DramaCandidate`、`DramaMismatchError(code="DRAMA_MISMATCH")`。

- [ ] **Step 1: 写失败测试**

```python
def test_match_uses_normalized_name_and_shanghai_minute() -> None:
    expected = datetime(2026, 8, 10, 6, 30, 59, tzinfo=timezone.utc)
    candidates = [
        DramaCandidate(" 剧Ａ ", datetime(2026, 8, 10, 14, 30, 1, tzinfo=SHANGHAI_TZ), "a", "2026-08-10 14:30", 0),
        DramaCandidate("剧A", datetime(2026, 8, 10, 14, 31, tzinfo=SHANGHAI_TZ), "b", "2026-08-10 14:31", 1),
    ]
    assert match_unique_drama("剧A", expected, candidates).locator_key == "a"

@pytest.mark.parametrize("candidates", [[], [candidate, duplicate]])
def test_zero_or_multiple_matches_raise_drama_mismatch(candidates) -> None:
    with pytest.raises(DramaMismatchError) as caught:
        match_unique_drama("剧A", expected, candidates)
    assert caught.value.code == "DRAMA_MISMATCH"
    assert caught.value.details["match_count"] != 1
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd backend; pytest -q tests/unit/test_drama_match.py`

Expected: FAIL，模块 `backend.domain.rules.drama_match` 不存在。

- [ ] **Step 3: 实现最小领域规则**

```python
@dataclass(frozen=True)
class DramaCandidate:
    drama_name: str
    available_time: datetime
    locator_key: str
    raw_time: str
    page_order: int

def normalize_drama_name(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split())

def shanghai_minute(value: datetime) -> datetime:
    return as_utc(value).astimezone(SHANGHAI_TZ).replace(second=0, microsecond=0)

def match_unique_drama(expected_name, expected_time, candidates):
    matches = [candidate for candidate in candidates if normalize_drama_name(candidate.drama_name) == normalize_drama_name(expected_name) and shanghai_minute(candidate.available_time) == shanghai_minute(expected_time)]
    if len(matches) != 1:
        raise DramaMismatchError(
            "同名剧分钟级匹配不唯一",
            details={
                "match_count": len(matches),
                "candidates": [
                    {
                        "drama_name": item.drama_name,
                        "minute": shanghai_minute(item.available_time).isoformat(),
                        "raw_time": item.raw_time,
                        "page_order": item.page_order,
                    }
                    for item in candidates
                ],
            },
        )
    return matches[0]
```

`DramaMismatchError` 继承 `DomainError`，固定 `code="DRAMA_MISMATCH"`，完整保留 `details`。

- [ ] **Step 4: 运行领域测试确认 GREEN**

Run: `cd backend; pytest -q tests/unit/test_drama_match.py`

Expected: PASS，覆盖唯一命中、秒忽略、UTC/上海转换、零匹配、多匹配和 NFKC 剧名标准化。

---

### Task 2: Tomato 端口显式传递任务时间

**Files:**
- Modify: `backend/src/backend/domain/ports/adapters.py`
- Modify: `backend/src/backend/application/services/tomato_extraction_service.py`
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Modify: `backend/src/backend/platforms/mock/mock_tomato.py`
- Test: `backend/tests/unit/test_tomato_extraction_service.py`
- Test: `backend/tests/unit/test_task_preparation_service.py`
- Test: `backend/tests/unit/test_mock_adapters.py`
- Test: `backend/tests/integration/test_tomato_extraction.py`

**Interfaces:**
- Consumes: Task 1 的分钟级匹配规则。
- Produces: `extract_iaa_link(drama_name, available_time, episode_count, selected_episode)`、`scan_iap_templates(drama_name, available_time)`、`generate_iap_link(drama_name, available_time, template)`。

- [ ] **Step 1: 写失败测试证明任务时间贯穿调用链**

```python
def test_scan_iap_passes_available_time_to_all_tomato_calls() -> None:
    tomato = RecordingTomato()
    target_time = datetime(2026, 8, 10, 14, 30, tzinfo=SHANGHAI_TZ)
    scan_iap("剧A", target_time, tomato, price_rules)
    assert tomato.calls == [
        ("scan", "剧A", target_time),
        ("generate", "剧A", target_time, "tpl-2.9"),
        ("generate", "剧A", target_time, "tpl-9.9"),
        ("iaa", "剧A", target_time, 1, 1),
    ]
```

并在 `test_task_preparation_service.py` 断言 `_task().available_time` 原样传入 Tomato fake。

- [ ] **Step 2: 运行相关测试确认 RED**

Run: `cd backend; pytest -q tests/unit/test_tomato_extraction_service.py tests/unit/test_task_preparation_service.py tests/unit/test_mock_adapters.py tests/integration/test_tomato_extraction.py`

Expected: FAIL，现有端口和服务不接受 `available_time`。

- [ ] **Step 3: 修改端口与调用链**

```python
def scan_iap(drama_name: str, available_time: datetime, tomato: TomatoAdapter, price_rules: list[TemplatePriceRule]) -> IapScanResult:
    templates = tomato.scan_iap_templates(drama_name, available_time)
    # 生成 IAP 与 IAA 时继续传入同一个 available_time
```

`TaskPreparationService._resolve_links()` 使用 `task.available_time`；Mock Adapter 接受时间但不改变确定性 URL。所有测试 fake 同步新签名，不添加默认时间以免生产调用遗漏。

- [ ] **Step 4: 运行相关测试确认 GREEN**

Run: `cd backend; pytest -q tests/unit/test_tomato_extraction_service.py tests/unit/test_task_preparation_service.py tests/unit/test_mock_adapters.py tests/integration/test_tomato_extraction.py`

Expected: PASS，且任务时间在 IAA/IAP 全链路可观察。

---

### Task 3: 番茄列表唯一选择与详情二次复核

**Files:**
- Create: `backend/src/backend/platforms/tomato/page_objects/drama_selection.py`
- Modify: `backend/src/backend/platforms/tomato/page_objects/free_entry.py`
- Modify: `backend/src/backend/platforms/tomato/page_objects/paid_entry.py`
- Modify: `backend/src/backend/platforms/tomato/tomato_adapter.py`
- Modify: `backend/src/backend/bootstrap/adapters.py`
- Modify: `configs/defaults/tomato_selectors.json`
- Test: `backend/tests/unit/test_tomato_adapter.py`
- Test: `backend/tests/unit/test_adapter_factory.py`

**Interfaces:**
- Consumes: Task 1 的 `DramaCandidate` 与 `match_unique_drama()`，Task 2 的带时间 Tomato 端口。
- Produces: `DramaSelectionPage.select_and_verify(drama_name, available_time) -> DramaCandidate`。

- [ ] **Step 1: 写失败测试覆盖两阶段安全门**

```python
def test_iaa_opens_only_exact_minute_candidate_and_verifies_detail() -> None:
    page = candidate_page([
        ["剧A", "2026-08-10 14:29", "/detail/old"],
        ["剧A", "2026-08-10 14:30", "/detail/right"],
    ], detail=["剧A", "2026-08-10 14:30"])
    adapter = make_adapter(page, dry_run=False)
    adapter.extract_iaa_link("剧A", target_time, 40, 1)
    assert page.clicked_detail_href == "/detail/right"
    assert page.generate_clicks == 1

@pytest.mark.parametrize("detail", [["剧A", "2026-08-10 14:31"], ["另一部剧", "2026-08-10 14:30"]])
def test_detail_mismatch_never_clicks_generate(detail) -> None:
    page = candidate_page([["剧A", "2026-08-10 14:30", "/detail/right"]], detail=detail)
    with pytest.raises(DramaMismatchError):
        make_adapter(page, dry_run=False).extract_iaa_link("剧A", target_time, 40, 1)
    assert page.generate_clicks == 0
```

增加 IAP 测试，分别断言 `scan_iap_templates` 与 `generate_iap_link` 都先调用同一个选择器；零匹配、多匹配和时间解析失败均不点击详情后的生成控件。

- [ ] **Step 2: 运行 Adapter 测试确认 RED**

Run: `cd backend; pytest -q tests/unit/test_tomato_adapter.py`

Expected: FAIL，缺少候选字段 selector 与 `DramaSelectionPage`。

- [ ] **Step 3: 实现共享两阶段选择器**

`DramaSelectionPage`：

1. 进入入口并精确搜索剧名；
2. 使用 `result_row` 内的 `result_drama_name`、`result_available_time` 和 `detail_link[href]` 读取候选；
3. 解析完整年月日时分（支持 `YYYY-MM-DD HH:mm[:ss]`、`YYYY/MM/DD HH:mm[:ss]`、`YYYY年MM月DD日 HH:mm[:ss]`）；
4. 调用 `match_unique_drama()`；
5. 按唯一 `href` 打开详情；
6. 读取 `detail_drama_name`、`detail_available_time`，构造单候选再次调用 `match_unique_drama()`；
7. 失败时调用 `page.screenshot()` 保存到 Adapter 注入的 artifact 目录，并将 `stage/raw_time/screenshot_path` 合并进 `DramaMismatchError.details`。

Free/paid Page Object 删除默认首条点击和重新跳转；Adapter 在每次 IAA 提取、IAP 扫描、IAP 生成之前统一调用 `select_and_verify()`。

新增 selector：

```json
{
  "result_drama_name": "[data-field='drama-name']",
  "result_available_time": "[data-field='available-time']",
  "detail_drama_name": "[data-field='drama-name']",
  "detail_available_time": "[data-field='available-time']"
}
```

- [ ] **Step 4: 运行 Adapter 测试确认 GREEN**

Run: `cd backend; pytest -q tests/unit/test_tomato_adapter.py`

Expected: PASS，唯一 href 被点击，详情不一致时所有生成按钮零调用，IAA/IAP 共用选择逻辑。

---

### Task 4: DRAMA_MISMATCH 状态、事件与端到端阻断

**Files:**
- Modify: `backend/src/backend/application/services/task_preparation_service.py`
- Modify: `backend/src/backend/application/services/worker_executor.py`
- Modify: `docs/rules/business-rules.md`
- Modify: `docs/workflows/full-workflow.md`
- Test: `backend/tests/unit/test_task_preparation_service.py`
- Test: `backend/tests/unit/test_worker_executor.py`
- Test: `backend/tests/integration/test_phase10_full_scenario.py`

**Interfaces:**
- Consumes: Task 1 的 `DramaMismatchError.details`。
- Produces: `PreparationOutcome(status, failure_code, details)`、持久化 `task.link_status="DRAMA_MISMATCH"`、Worker `failure_code="DRAMA_MISMATCH"`、包含候选和失败阶段的 `LINK_EXTRACTION` ERROR 事件。

- [ ] **Step 1: 写失败测试覆盖人工处理与后续零调用**

```python
def test_drama_mismatch_is_saved_and_never_writes_links_or_enqueues() -> None:
    tomato = MismatchTomato(details={"stage": "DETAIL", "match_count": 0})
    result = service(tomato).prepare_task(task, dry_run=False, now=task.available_time)
    assert result.status == "MANUAL_REVIEW"
    assert result.failure_code == "DRAMA_MISMATCH"
    assert task.link_status == "DRAMA_MISMATCH"
    assert feishu.writes == []
    assert queue.items == {}

def test_worker_preserves_drama_mismatch_failure_code() -> None:
    outcome = execute_mismatched_task()
    assert outcome.status == "MANUAL_REVIEW"
    assert outcome.failure_code == "DRAMA_MISMATCH"
    assert outcome.retry_safe is False
    assert outcome.events[0].context_json["stage"] == "DETAIL"
```

- [ ] **Step 2: 运行阻断测试确认 RED**

Run: `cd backend; pytest -q tests/unit/test_task_preparation_service.py tests/unit/test_worker_executor.py tests/integration/test_phase10_full_scenario.py`

Expected: FAIL，现有准备服务把空链接统一记为 `FAILED`，Worker 未保留匹配失败码和详情。

- [ ] **Step 3: 实现最小状态映射与审计事件**

`TaskPreparationService.prepare_task()` 返回不可变结果：

```python
@dataclass(frozen=True)
class PreparationOutcome:
    status: str
    failure_code: str | None = None
    details: dict = field(default_factory=dict)
```

它捕获 `DramaMismatchError`，保存 `MANUAL_REVIEW/DRAMA_MISMATCH`，不回填、不入队，并把错误码与详情放入本次返回值；`prepare()` 和 Worker 均消费该返回值，不使用跨任务共享状态。Worker 构造：

```python
ExecutionOutcome(
    status=STATUS_MANUAL_REVIEW,
    failure_code="DRAMA_MISMATCH",
    retry_safe=False,
    events=[ExecutionEvent(event_type="LINK_EXTRACTION", level=ERROR, context_json=details)],
)
```

文档明确分钟级匹配、列表/详情二次校验以及零/多匹配禁止自动重试。

- [ ] **Step 4: 运行定向测试确认 GREEN**

Run: `cd backend; pytest -q tests/unit/test_drama_match.py tests/unit/test_tomato_extraction_service.py tests/unit/test_tomato_adapter.py tests/unit/test_task_preparation_service.py tests/unit/test_worker_executor.py tests/integration/test_tomato_extraction.py tests/integration/test_phase10_full_scenario.py`

Expected: PASS。

- [ ] **Step 5: 全量验证与工作区审计**

Run:

```powershell
cd backend
pytest -q
python -m compileall -q src tests
cd ..\dashboard
npm test -- --run
npm run build
cd ..
git diff --check
codegraph sync .
codegraph status .
git status --short
```

Expected: 后端/前端测试 0 failed，构建和编译退出码 0，CodeGraph 索引最新；记录前端大包警告但不做无关重构。

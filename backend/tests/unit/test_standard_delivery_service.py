"""标准投放执行服务单元测试：fakes 注入各依赖。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.application.services import submit_guard as submit_guard_module
from backend.application.services.plan_validation_service import (
    ValidationIssue,
    ValidationReport,
)
from backend.application.services.standard_delivery_service import (
    COMPLETED,
    DRY_RUN,
    MANUAL_REVIEW,
    VALIDATION_FAILED,
    StandardDeliveryService,
)
from backend.domain.errors.domain_error import ExternalAdapterError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.plans.plan_spec import MaterialPlan, PlanSpec
from backend.domain.ports.adapters import DramaAsset
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter


class FakeValidation:
    """固定返回预置 ValidationReport 的校验 fake。"""

    def __init__(self, report: ValidationReport) -> None:
        self._report = report

    def validate(self, spec: PlanSpec, cid_configs: list[dict]) -> ValidationReport:
        return self._report


class RecordingDeliveryAdapter(MockDeliverySystemAdapter):
    """记录 submit_plan 调用次数的投放系统 Mock。"""

    def __init__(self) -> None:
        super().__init__()
        self.submit_calls = 0

    def submit_plan(self, plan_spec: PlanSpec) -> str:
        self.submit_calls += 1
        return super().submit_plan(plan_spec)


class StuckDeliveryAdapter:
    """轮询永远不完成的投放系统 fake。"""

    def find_or_create_drama_asset(self, drama_name: str, link: str) -> DramaAsset:
        return DramaAsset(
            delivery_drama_id="dd-1", drama_name=drama_name, link=link
        )

    def ensure_promotion_config(
        self,
        asset_id: str,
        link_type: str,
        link: str,
        drama_name: str,
        platform: str,
    ) -> str:
        return f"cfg-{link_type}"

    def submit_plan(self, plan_spec: PlanSpec) -> str:
        return "task-ext-timeout"

    def poll_task_status(self, external_task_id: str) -> str:
        return "SUBMITTED"


class FailingDeliveryAdapter(StuckDeliveryAdapter):
    """提交阶段抛异常且未生成外部任务 ID 的投放系统 fake。"""

    def submit_plan(self, plan_spec: PlanSpec) -> str:
        raise ExternalAdapterError("投放提交失败")


class FakeLedgerRepository:
    """内存态 LedgerRepository fake。"""

    def __init__(self) -> None:
        self._ledgers: dict[str, TaskLedger] = {}

    def add(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def get(self, ledger_id: str) -> TaskLedger | None:
        return self._ledgers.get(ledger_id)

    def update(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def list_by_task(self, task_id: str) -> list[TaskLedger]:
        return [ledger for ledger in self._ledgers.values() if ledger.task_id == task_id]

    def list_all(self) -> list[TaskLedger]:
        return list(self._ledgers.values())


class FakeTaskRepository:
    """内存态 TaskRepository fake。"""

    def __init__(self, tasks: dict[str, DramaTask] | None = None) -> None:
        self._tasks = tasks or {}

    def get(self, task_id: str) -> DramaTask | None:
        return self._tasks.get(task_id)

    def update(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task


def _spec() -> PlanSpec:
    return PlanSpec(
        drama_name="剧A",
        platform="TOMATO",
        task_name="番茄#端免剧A20260807ubr-1",
        link_set={"IAA": "mock://iaa/剧A"},
        account_cids=["cid-1"],
        material_groups=MaterialPlan(1, 2, 3, 1, 3),
        expected_project_count=3,
    )


def _task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
    )


def _service(
    *,
    validation: FakeValidation,
    delivery,
    feishu: MockFeishuAdapter,
    ledger_repo: FakeLedgerRepository,
    task_repo: FakeTaskRepository,
) -> StandardDeliveryService:
    return StandardDeliveryService(
        validation,
        delivery,
        MockOceanEngineAdapter(),
        submit_guard_module,
        feishu,
        ledger_repo,
        task_repo,
    )


class TestStandardDeliveryService:
    """标准投放执行状态与 M=1 闸门。"""

    def test_validation_failure_returns_validation_failed_without_platform_calls(
        self,
    ) -> None:
        issues = [ValidationIssue(code="LINK_SET_EMPTY", message="空", field="link_set")]
        delivery = RecordingDeliveryAdapter()
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(
            validation=FakeValidation(ValidationReport(passed=False, issues=issues)),
            delivery=delivery,
            feishu=feishu,
            ledger_repo=ledger_repo,
            task_repo=FakeTaskRepository({"task-1": _task()}),
        )

        outcome = service.execute(
            _spec(), [], "task-1", True, True, "worker-1"
        )

        assert outcome.status == VALIDATION_FAILED
        assert outcome.issues == issues
        assert outcome.external_task_id is None
        assert outcome.ledger_id is None
        assert delivery.submit_calls == 0
        assert feishu.read_status("task-1") == "PENDING"
        assert ledger_repo.list_all() == []

    def test_guard_disabled_returns_dry_run_without_m(self) -> None:
        delivery = RecordingDeliveryAdapter()
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(
            validation=FakeValidation(ValidationReport(passed=True, issues=[])),
            delivery=delivery,
            feishu=feishu,
            ledger_repo=ledger_repo,
            task_repo=FakeTaskRepository({"task-1": _task()}),
        )

        outcome = service.execute(
            _spec(), [], "task-1", False, True, "worker-1"
        )

        assert outcome.status == DRY_RUN
        assert outcome.external_task_id is None
        assert outcome.ledger_id is None
        assert delivery.submit_calls == 0
        assert feishu.read_status("task-1") == "PENDING"
        assert ledger_repo.list_all() == []

    def test_success_writes_m_and_success_ledger(self) -> None:
        delivery = RecordingDeliveryAdapter()
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(
            validation=FakeValidation(ValidationReport(passed=True, issues=[])),
            delivery=delivery,
            feishu=feishu,
            ledger_repo=ledger_repo,
            task_repo=FakeTaskRepository({"task-1": _task()}),
        )

        outcome = service.execute(
            _spec(), [], "task-1", True, True, "worker-1"
        )

        assert outcome.status == COMPLETED
        assert outcome.external_task_id
        assert outcome.ledger_id
        assert delivery.submit_calls == 1
        assert feishu.read_status("task-1") == "OK"
        ledgers = ledger_repo.list_all()
        assert len(ledgers) == 1
        assert ledgers[0].final_status == COMPLETED
        assert ledgers[0].task_id == "task-1"
        assert ledgers[0].external_task_id == outcome.external_task_id

    def test_timeout_returns_manual_review_without_m(self) -> None:
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(
            validation=FakeValidation(ValidationReport(passed=True, issues=[])),
            delivery=StuckDeliveryAdapter(),
            feishu=feishu,
            ledger_repo=ledger_repo,
            task_repo=FakeTaskRepository({"task-1": _task()}),
        )

        outcome = service.execute(
            _spec(), [], "task-1", True, True, "worker-1"
        )

        assert outcome.status == MANUAL_REVIEW
        assert outcome.external_task_id == "task-ext-timeout"
        assert outcome.ledger_id is None
        assert feishu.read_status("task-1") == "PENDING"
        assert ledger_repo.list_all() == []

    def test_submit_exception_returns_manual_review_without_m(self) -> None:
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(
            validation=FakeValidation(ValidationReport(passed=True, issues=[])),
            delivery=FailingDeliveryAdapter(),
            feishu=feishu,
            ledger_repo=ledger_repo,
            task_repo=FakeTaskRepository({"task-1": _task()}),
        )

        outcome = service.execute(
            _spec(), [], "task-1", True, True, "worker-1"
        )

        assert outcome.status == MANUAL_REVIEW
        assert outcome.external_task_id is None
        assert outcome.ledger_id is None
        assert feishu.read_status("task-1") == "PENDING"
        assert ledger_repo.list_all() == []

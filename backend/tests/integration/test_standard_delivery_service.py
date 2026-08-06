"""标准投放执行服务集成测试：Mock adapters + MockFeishu 全链路。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.services import submit_guard as submit_guard_module
from backend.application.services.plan_validation_service import (
    PlanValidationService,
)
from backend.application.services.standard_delivery_service import (
    COMPLETED,
    DRY_RUN,
    StandardDeliveryService,
)
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.plans.plan_spec import MaterialPlan, PlanSpec
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter

UTC = timezone.utc
NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


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
        drama_name="我的剧",
        platform="TOMATO",
        task_name="番茄#端免我的剧20260807ubr-1",
        link_set={
            "IAA": "https://iaa/1",
            "9.9": "https://iap/9.9",
            "2.9": "https://iap/2.9",
        },
        account_cids=[
            "cid-b1",
            "cid-b4",
            "cid-b7",
            "cid-bx",
            "cid-iap-9-9",
            "cid-iap-2-9",
        ],
        material_groups=MaterialPlan(1, 2, 3, 1, 3),
        expected_project_count=3,
    )


def _cid_config(cid: str, delivery_type: str) -> dict:
    return {
        "subject": "主体A",
        "delivery_type": delivery_type,
        "cid": cid,
        "ad_preset": "预设A",
        "douyin_account": "B1",
        "account_open_preset": "开户A",
        "effective_from": NOW - timedelta(days=1),
        "enabled": True,
    }


def _cid_configs() -> list[dict]:
    delivery_types = {
        "cid-b1": "IAA",
        "cid-b4": "IAA",
        "cid-b7": "IAA",
        "cid-bx": "IAA",
        "cid-iap-9-9": "B1-9.9",
        "cid-iap-2-9": "B2-2.9",
    }
    return [
        _cid_config(cid, delivery_types[cid])
        for cid in _spec().account_cids
    ]


def _task() -> DramaTask:
    return DramaTask(
        id="task-8-3",
        drama_name="我的剧",
        platform="TOMATO",
        available_time=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
    )


def _service(
    feishu: MockFeishuAdapter,
    ledger_repo: FakeLedgerRepository,
    *,
    allow_final_submit: bool | None = True,
    use_real_adapters: bool | None = True,
) -> StandardDeliveryService:
    return StandardDeliveryService(
        PlanValidationService(now_provider=lambda: NOW),
        MockDeliverySystemAdapter(poll_rounds_before_completed=1),
        MockOceanEngineAdapter(),
        submit_guard_module,
        feishu,
        ledger_repo,
        FakeTaskRepository({"task-8-3": _task()}),
        allow_final_submit=allow_final_submit,
        use_real_adapters=use_real_adapters,
    )


class TestStandardDeliveryServiceIntegration:
    """Mock 全链路验收。"""

    def test_success_writes_m_and_ledger(self) -> None:
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(feishu, ledger_repo)

        outcome = service.execute(
            _spec(),
            _cid_configs(),
            "task-8-3",
            "worker-1",
        )

        assert outcome.status == COMPLETED
        assert outcome.external_task_id
        assert outcome.ledger_id
        assert feishu.read_status("task-8-3") == "OK"
        ledgers = ledger_repo.list_all()
        assert len(ledgers) == 1
        assert ledgers[0].final_status == COMPLETED
        assert ledgers[0].task_id == "task-8-3"

    def test_guard_disabled_returns_dry_run_without_m(self) -> None:
        feishu = MockFeishuAdapter()
        ledger_repo = FakeLedgerRepository()
        service = _service(
            feishu,
            ledger_repo,
            allow_final_submit=False,
            use_real_adapters=True,
        )

        outcome = service.execute(
            _spec(),
            _cid_configs(),
            "task-8-3",
            "worker-1",
        )

        assert outcome.status == DRY_RUN
        assert outcome.external_task_id is None
        assert outcome.ledger_id is None
        assert feishu.read_status("task-8-3") == "PENDING"
        assert ledger_repo.list_all() == []

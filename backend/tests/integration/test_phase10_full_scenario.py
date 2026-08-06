"""Phase 10 全链路验收：Worker 真实编排执行器 + Mock 全场景。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy.orm import Session

from backend.application.services.delivery_scheduler import DeliveryScheduler
from backend.application.services.queue_cycle import advance_queue
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.worker_execution import WorkerExecutionService
from backend.application.services.worker_executor import build_worker_executor
from backend.bootstrap.adapters import AdapterBundle
from backend.domain.execution.execution_event import EventLevel
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.rules.account_block import AccountRow
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.infrastructure.config.settings import PROJECT_ROOT, Settings
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.repositories.execution_repository import (
    SqlAlchemyExecutionRepository,
)
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"
UTC = timezone.utc
NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
WORKER_ID = "worker-phase10"


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """临时 SQLite + Alembic 迁移 + 默认规则 seed。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_url = f"sqlite:///{Path(tmpdir) / 'phase10.db'}"
        run_migrations(db_url)
        engine = create_app_engine(db_url)
        session = Session(engine)
        try:
            seed_rules_from_defaults(session, DEFAULTS_PATH)
            session.commit()
            yield session
        finally:
            session.close()
            engine.dispose()


def _task(task_id: str, drama_name: str, platform: str) -> DramaTask:
    return DramaTask(
        id=task_id,
        drama_name=drama_name,
        platform=platform,
        available_time=datetime(2026, 8, 7, 10, 0, tzinfo=UTC),
    )


def _bundle(task: DramaTask) -> AdapterBundle:
    return AdapterBundle(
        feishu=MockFeishuAdapter(tasks=[task]),
        tomato=MockTomatoAdapter(),
        delivery=MockDeliverySystemAdapter(),
        ocean=MockOceanEngineAdapter(),
    )


def _occupied_account_rows() -> list[AccountRow]:
    """全部行已占用，保证没有任何可用 IAA/IAP 块。"""
    groups = (
        "B1", "B1", "B1", "B4", "B4", "B4", "B7", "B7", "B7", "BX",
        "B1-9.9", "B1-9.9", "B1-9.9", "B2-2.9", "B2-2.9", "B2-2.9",
    )
    return [
        AccountRow(
            row_number=index,
            name=f"占用-{group}-{index}",
            cid=f"MOCK-CID-OCCUPIED-{index}",
            group=group,
            enabled=True,
            is_test=False,
            drama_name="已占用剧",
        )
        for index, group in enumerate(groups, start=1)
    ]


def _enqueue(session: Session, bundle: AdapterBundle):
    """调度扫描 + 队列推进，返回领取到的队列项。"""
    queue_repo = SqlAlchemyQueueRepository(session)
    task_repo = SqlAlchemyTaskRepository(session)
    DeliveryScheduler(bundle.feishu, task_repo, queue_repo).tick(NOW)
    _enqueued, claimed = advance_queue(
        session, queue_repo, NOW, WORKER_ID, lease_seconds=60
    )
    return claimed


def _process(
    session: Session,
    bundle: AdapterBundle,
    claimed: QueueItem,
    *,
    account_rows: list[AccountRow] | None = None,
    settings: Settings | None = None,
) -> tuple:
    """用真实编排 executor 处理已领取任务并提交事务。"""
    settings = settings or Settings(allow_final_submit=True)
    queue_repo = SqlAlchemyQueueRepository(session)
    task_repo = SqlAlchemyTaskRepository(session)
    ledger_repo = SqlAlchemyLedgerRepository(session)
    event_repo = SqlAlchemyExecutionRepository(session)
    service = WorkerExecutionService(
        build_worker_executor(
            settings,
            bundle,
            session,
            account_rows=account_rows,
        ),
        queue_repo,
        task_repo,
        ledger_repo,
        event_repo,
        WORKER_ID,
    )
    result = service.process_claimed(claimed, NOW)
    session.commit()
    return result, queue_repo, task_repo, ledger_repo, event_repo


class TestPhase10FullScenario:
    """Worker 真实编排执行器 Mock 全链路验收。"""

    def test_tomato_full_chain_completes_without_write_links(
        self, db_session: Session
    ) -> None:
        task = _task("task-phase10-tomato-001", "验收短剧", "TOMATO")
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session, bundle, claimed
        )

        assert result.final_queue_state == QueueState.COMPLETED
        assert queue_repo.get(claimed.id).state == QueueState.COMPLETED
        assert task_repo.get(task.id).status == TaskStatus.COMPLETED
        ledgers = ledger_repo.list_by_task(task.id)
        assert len(ledgers) == 1
        assert ledgers[0].final_status == "COMPLETED"
        assert ledgers[0].product_id
        assert ledgers[0].external_task_id
        assert ledgers[0].task_name
        events = event_repo.list_events(task_id=task.id)
        assert len(events) >= 1
        assert {event.event_type for event in events} == {
            "LINK_EXTRACTION",
            "ACCOUNT_ALLOCATION",
            "DELIVERY",
        }
        assert bundle.feishu.written_links == {}

    def test_tomato_dry_run_default_settings_completes_without_submit(
        self, db_session: Session
    ) -> None:
        task = _task("task-phase10-dryrun-001", "验收短剧D", "TOMATO")
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session,
            bundle,
            claimed,
            settings=Settings(),
        )

        assert result.final_queue_state == QueueState.COMPLETED
        assert queue_repo.get(claimed.id).state == QueueState.COMPLETED
        assert task_repo.get(task.id).status == TaskStatus.COMPLETED
        assert len(ledger_repo.list_by_task(task.id)) == 1
        delivery_events = event_repo.list_events(
            task_id=task.id,
        )
        delivery = next(
            event for event in delivery_events if event.event_type == "DELIVERY"
        )
        assert delivery.level == EventLevel.WARNING
        assert "安全开关拦截" in delivery.message
        assert bundle.feishu.written_links == {}

    def test_all_accounts_occupied_returns_manual_review(
        self, db_session: Session
    ) -> None:
        task = _task("task-phase10-occupied-001", "验收短剧B", "TOMATO")
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session,
            bundle,
            claimed,
            account_rows=_occupied_account_rows(),
        )

        assert result.final_queue_state == QueueState.MANUAL_REVIEW
        assert queue_repo.get(claimed.id).state == QueueState.MANUAL_REVIEW
        assert task_repo.get(task.id).status == TaskStatus.MANUAL_REVIEW
        assert ledger_repo.list_by_task(task.id) == []
        errors = event_repo.list_events(
            task_id=task.id, level=EventLevel.ERROR
        )
        assert any(
            event.event_type == "ACCOUNT_ALLOCATION" for event in errors
        )
        assert bundle.feishu.written_links == {}

    def test_jubian_returns_manual_review_with_error(
        self, db_session: Session
    ) -> None:
        task = _task("task-phase10-jubian-001", "剧变短剧", "JUBIAN")
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session, bundle, claimed
        )

        assert result.final_queue_state == QueueState.MANUAL_REVIEW
        assert task_repo.get(task.id).status == TaskStatus.MANUAL_REVIEW
        assert ledger_repo.list_by_task(task.id) == []
        errors = event_repo.list_events(
            task_id=task.id, level=EventLevel.ERROR
        )
        assert len(errors) >= 1
        assert "JUBIAN" in errors[0].message
        assert bundle.feishu.written_links == {}

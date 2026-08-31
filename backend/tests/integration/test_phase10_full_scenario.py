"""Phase 10 全链路验收：Worker 真实编排执行器 + Mock 全场景。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import select
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
from backend.infrastructure.database.models.account import AccountUsageRecord
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
from backend.platforms.mock.mock_account_table import MOCK_ACCOUNT_ROWS

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"
UTC = timezone.utc
NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
WORKER_ID = "worker-phase10"


class Phase10DeliveryConfig:
    def mapping_proposal(self) -> list[dict]:
        return [
            {
                "cid": row.cid,
                "company": "测试主体",
                "ad_preset": f"ad-{row.cid}",
                "open_preset": f"open-{row.cid}",
                "douyin_account": f"douyin-{row.cid}",
            }
            for row in MOCK_ACCOUNT_ROWS
        ]

    def task_resources(self, drama_name: str) -> dict:
        return {
            "material_ids": [f"{drama_name}-material-{index}" for index in range(3)],
            "title_packages": [f"{drama_name}-title-{index}" for index in range(6)],
        }


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
        queue_repo, NOW, WORKER_ID, lease_seconds=60
    )
    return claimed


def _process(
    session: Session,
    bundle: AdapterBundle,
    claimed: QueueItem,
    *,
    account_rows: list[AccountRow] | None = None,
    settings: Settings | None = None,
    use_real_adapters: bool = False,
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
            use_real_adapters=use_real_adapters,
            poll_interval_seconds=0,
            delivery_config=Phase10DeliveryConfig(),
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

    def test_tomato_full_chain_freezes_and_writes_links_once(
        self, db_session: Session
    ) -> None:
        task = _task("task-phase10-tomato-001", "验收短剧", "TOMATO")
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session, bundle, claimed, use_real_adapters=True
        )

        assert result.final_queue_state == QueueState.COMPLETED
        assert queue_repo.get(claimed.id).state == QueueState.COMPLETED
        assert task_repo.get(task.id).status == TaskStatus.COMPLETED
        ledgers = ledger_repo.list_by_task(task.id)
        assert len(ledgers) == 1
        assert ledgers[0].final_status == "COMPLETED"
        # 商品库由投放系统自动配置，Worker 不再创建或保存 product_id。
        assert ledgers[0].product_id == ""
        assert ledgers[0].external_task_id
        assert ledgers[0].task_name
        events = event_repo.list_events(task_id=task.id)
        assert len(events) >= 1
        assert {event.event_type for event in events} == {
            "LINK_EXTRACTION",
            "ACCOUNT_ALLOCATION",
            "DELIVERY",
        }
        assert set(bundle.feishu.written_links[task.id]) >= {"IAA"}
        usages = db_session.execute(select(AccountUsageRecord)).scalars().all()
        assert len(usages) == 16
        assert {usage.task_id for usage in usages} == {task.id}

    def test_worker_consumes_frozen_links_without_tomato_call(
        self, db_session: Session
    ) -> None:
        class ExplodingTomato:
            def __getattr__(self, name):
                raise AssertionError(f"冻结后不应再次调用番茄: {name}")

        task = _task("task-phase10-frozen-001", "冻结短剧", "TOMATO")
        task.link_set = {"IAA": "aweme://frozen"}
        task.link_status = "VALIDATED"
        bundle = AdapterBundle(
            feishu=MockFeishuAdapter(tasks=[task]),
            tomato=ExplodingTomato(),
            delivery=MockDeliverySystemAdapter(),
            ocean=MockOceanEngineAdapter(),
        )
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, *_ = _process(
            db_session,
            bundle,
            claimed,
            use_real_adapters=True,
        )

        assert result.final_queue_state == QueueState.COMPLETED
        assert bundle.feishu.written_links == {}

    def test_tomato_dry_run_explicit_settings_does_not_complete(
        self, db_session: Session, monkeypatch
    ) -> None:
        monkeypatch.delenv("WORKBUDDY_ALLOW_FINAL_SUBMIT", raising=False)
        task = _task("task-phase10-dryrun-001", "验收短剧D", "TOMATO")
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session,
            bundle,
            claimed,
            settings=Settings(allow_final_submit=False),
            use_real_adapters=False,
        )

        assert result.final_queue_state == QueueState.DRY_RUN
        assert queue_repo.get(claimed.id).state == QueueState.DRY_RUN
        assert task_repo.get(task.id).status == TaskStatus.DRY_RUN
        assert ledger_repo.list_by_task(task.id) == []
        delivery_events = event_repo.list_events(
            task_id=task.id,
        )
        delivery = next(
            event for event in delivery_events if event.event_type == "DELIVERY"
        )
        assert delivery.level == EventLevel.WARNING
        assert "安全开关拦截" in delivery.message
        assert bundle.feishu.written_links == {}
        assert db_session.execute(select(AccountUsageRecord)).scalars().all() == []

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

    def test_jubian_uses_sheet_links_without_opening_tomato(
        self, db_session: Session
    ) -> None:
        task = _task("task-phase10-jubian-001", "剧变短剧", "JUBIAN")
        task.source_links = {
            "IAA": (
                "aweme://playlet?playlet_id=123&version=2"
                "&advertise_param=abc&hash_res=def"
            )
        }
        bundle = _bundle(task)
        claimed = _enqueue(db_session, bundle)
        assert claimed is not None

        result, queue_repo, task_repo, ledger_repo, event_repo = _process(
            db_session, bundle, claimed, use_real_adapters=True
        )

        assert result.final_queue_state == QueueState.COMPLETED
        assert task_repo.get(task.id).status == TaskStatus.COMPLETED
        assert len(ledger_repo.list_by_task(task.id)) == 1
        assert bundle.feishu.written_links == {}

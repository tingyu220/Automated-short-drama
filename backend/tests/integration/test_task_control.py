"""队列控制集成测试 —— 临时 SQLite + Alembic."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend.application.services.task_control_service import (
    cancel_task,
    mark_manual_review,
    pause_task,
    resume_task,
    retry_task,
)
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)


def _setup_temp_db(db_url: str):
    """创建临时数据库并运行 Alembic 迁移至 head."""
    engine = create_app_engine(db_url)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option(
        "script_location", str(Path("alembic").resolve())
    )
    command.upgrade(alembic_cfg, "head")
    return engine


def _create_task(session: Session, task_id: str, now: datetime) -> None:
    """插入关联 DramaTask。"""
    task_repo = SqlAlchemyTaskRepository(session)
    task = DramaTask(
        id=task_id,
        drama_name="测试剧",
        platform="TOMATO",
        available_time=now,
        status=TaskStatus.RUNNING,
    )
    task_repo.add(task)


def _create_queue_item(
    session: Session,
    item_id: str,
    task_id: str,
    state: str,
    now: datetime,
    claimed_by: str | None = None,
    attempt_count: int = 0,
) -> None:
    """插入指定状态的队列项。"""
    queue_repo = SqlAlchemyQueueRepository(session)
    lease_until = now + timedelta(seconds=60) if claimed_by else None
    item = QueueItem(
        id=item_id,
        task_id=task_id,
        state=state,
        claimed_by=claimed_by,
        lease_until=lease_until,
        attempt_count=attempt_count,
    )
    queue_repo.add(item)


class TestTaskControlIntegration:
    """验证暂停/恢复/取消/重试/人工处理在真实 SQLite 中的行为。"""

    def test_pause_resume_cancel_flow(self):
        """QUEUED 项可暂停、恢复、取消，字段正确清空。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                item_id = str(uuid.uuid4())

                with Session(engine) as s:
                    _create_task(s, task_id, now)
                    _create_queue_item(
                        s, item_id, task_id, QueueState.QUEUED, now
                    )
                    queue_repo = SqlAlchemyQueueRepository(s)
                    task_repo = SqlAlchemyTaskRepository(s)

                    paused = pause_task(
                        queue_repo, task_repo, item_id, "worker-1"
                    )
                    s.commit()
                    assert paused.state == QueueState.PAUSED
                    assert paused.claimed_by is None
                    assert paused.lease_until is None

                    resumed = resume_task(queue_repo, task_repo, item_id)
                    s.commit()
                    assert resumed.state == QueueState.QUEUED

                    cancelled = cancel_task(
                        queue_repo, task_repo, item_id, "worker-1"
                    )
                    s.commit()
                    assert cancelled.state == QueueState.CANCELLED
                    assert cancelled.claimed_by is None
                    assert cancelled.lease_until is None

                    persisted = queue_repo.get(item_id)
                    assert persisted is not None
                    assert persisted.state == QueueState.CANCELLED
                    assert persisted.claimed_by is None
                    assert persisted.lease_until is None
            finally:
                engine.dispose()

    def test_claimed_pause_and_worker_guard(self):
        """CLAIMED 项暂停需 worker 匹配，否则抛 ConflictError 且状态不变。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                item_id = str(uuid.uuid4())

                with Session(engine) as s:
                    _create_task(s, task_id, now)
                    _create_queue_item(
                        s,
                        item_id,
                        task_id,
                        QueueState.CLAIMED,
                        now,
                        claimed_by="worker-A",
                    )
                    queue_repo = SqlAlchemyQueueRepository(s)
                    task_repo = SqlAlchemyTaskRepository(s)

                    with pytest.raises(ConflictError):
                        pause_task(queue_repo, task_repo, item_id, "worker-B")

                    paused = pause_task(
                        queue_repo, task_repo, item_id, "worker-A"
                    )
                    s.commit()
                    assert paused.state == QueueState.PAUSED
                    assert paused.claimed_by is None
                    assert paused.lease_until is None
            finally:
                engine.dispose()

    def test_mark_manual_review_then_retry(self):
        """RUNNING 项转人工后重试回到 QUEUED，重试次数重置、领取字段清空。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                item_id = str(uuid.uuid4())

                with Session(engine) as s:
                    _create_task(s, task_id, now)
                    _create_queue_item(
                        s,
                        item_id,
                        task_id,
                        QueueState.RUNNING,
                        now,
                        claimed_by="worker-1",
                        attempt_count=2,
                    )
                    queue_repo = SqlAlchemyQueueRepository(s)
                    task_repo = SqlAlchemyTaskRepository(s)

                    manual = mark_manual_review(
                        queue_repo, task_repo, item_id, "worker-1"
                    )
                    s.commit()
                    assert manual.state == QueueState.MANUAL_REVIEW
                    assert manual.claimed_by is None
                    assert manual.lease_until is None

                    retried = retry_task(queue_repo, task_repo, item_id)
                    s.commit()
                    assert retried.state == QueueState.QUEUED
                    assert retried.attempt_count == 0
                    assert retried.claimed_by is None
                    assert retried.lease_until is None
            finally:
                engine.dispose()

    def test_retry_failed_and_retry_wait(self):
        """FAILED 与 RETRY_WAIT 项均可重试，重置次数并清空领取字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                failed_id = str(uuid.uuid4())
                retry_wait_id = str(uuid.uuid4())

                with Session(engine) as s:
                    _create_task(s, task_id, now)
                    _create_queue_item(
                        s,
                        failed_id,
                        task_id,
                        QueueState.FAILED,
                        now,
                        claimed_by="worker-1",
                        attempt_count=3,
                    )
                    _create_queue_item(
                        s,
                        retry_wait_id,
                        task_id,
                        QueueState.RETRY_WAIT,
                        now,
                        claimed_by="worker-1",
                        attempt_count=2,
                    )
                    queue_repo = SqlAlchemyQueueRepository(s)
                    task_repo = SqlAlchemyTaskRepository(s)

                    failed = retry_task(queue_repo, task_repo, failed_id)
                    s.commit()
                    assert failed.state == QueueState.QUEUED
                    assert failed.attempt_count == 0
                    assert failed.claimed_by is None
                    assert failed.lease_until is None

                    retry_wait = retry_task(
                        queue_repo, task_repo, retry_wait_id
                    )
                    s.commit()
                    assert retry_wait.state == QueueState.QUEUED
                    assert retry_wait.attempt_count == 0
                    assert retry_wait.claimed_by is None
                    assert retry_wait.lease_until is None
            finally:
                engine.dispose()

    def test_terminal_and_missing_errors(self):
        """终态取消与不存在项分别抛 ConflictError/NotFoundError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                item_id = str(uuid.uuid4())

                with Session(engine) as s:
                    _create_task(s, task_id, now)
                    _create_queue_item(
                        s, item_id, task_id, QueueState.COMPLETED, now
                    )
                    queue_repo = SqlAlchemyQueueRepository(s)
                    task_repo = SqlAlchemyTaskRepository(s)

                    with pytest.raises(ConflictError):
                        cancel_task(queue_repo, task_repo, item_id, "worker-1")

                    with pytest.raises(NotFoundError):
                        pause_task(
                            queue_repo, task_repo, "missing", "worker-1"
                        )
            finally:
                engine.dispose()

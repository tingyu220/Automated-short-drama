"""队列全流程集成验收 —— 临时 SQLite + Alembic."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.completion_service import complete_task
from backend.application.services.queue_cycle import advance_queue
from backend.application.services.recovery_service import recover_expired
from backend.domain.queue.queue_item import QueueState
from backend.domain.tasks.drama_task import TaskStatus
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
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


class TestQueueFullScenario:
    """入队 -> 领取 -> 崩溃恢复 -> 再领取 -> 完成出队的全流程验收."""

    def test_full_queue_cycle(self):
        """验证队列从 WAITING_TIME 到 COMPLETED 的完整生命周期与台账落库."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                past = now - timedelta(hours=1)
                task_id = str(uuid.uuid4())
                queue_id = str(uuid.uuid4())

                # 1. 创建已到点的 DramaTask 与 WAITING_TIME QueueItem
                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, "
                            "available_time, status) "
                            "VALUES (:tid, 'integration-drama', 'TOMATO', :at, :status)"
                        ),
                        {"tid": task_id, "at": past, "status": TaskStatus.WAITING_TIME},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at) "
                            "VALUES (:qid, :tid, :state, 0, :at)"
                        ),
                        {
                            "qid": queue_id,
                            "tid": task_id,
                            "state": QueueState.WAITING_TIME,
                            "at": past,
                        },
                    )

                # 2. 第一次推进：WAITING_TIME -> QUEUED -> CLAIMED
                with Session(engine, expire_on_commit=False) as session:
                    queue_repo = SqlAlchemyQueueRepository(session)
                    enqueued, claimed = advance_queue(
                        queue_repo, now, "worker-1", lease_seconds=60
                    )
                    session.commit()

                    assert [item.id for item in enqueued] == [queue_id]
                    assert enqueued[0].state == QueueState.QUEUED
                    assert claimed is not None
                    assert claimed.id == queue_id
                    assert claimed.state == QueueState.CLAIMED
                    assert claimed.claimed_by == "worker-1"
                    assert claimed.lease_until == now + timedelta(seconds=60)

                # 3. 模拟 Worker 崩溃：租约过期
                with Session(engine) as session:
                    session.execute(
                        sa_text(
                            "UPDATE queue_item SET lease_until=:past "
                            "WHERE id=:qid"
                        ),
                        {
                            "qid": queue_id,
                            "past": now - timedelta(seconds=10),
                        },
                    )
                    session.commit()

                # 4. 崩溃恢复：CLAIMED -> QUEUED，attempt_count=1
                with Session(engine, expire_on_commit=False) as session:
                    result = recover_expired(session, now)
                    session.commit()

                    assert len(result.requeued) == 1
                    assert result.requeued[0].id == queue_id
                    assert result.requeued[0].state == QueueState.QUEUED
                    assert result.requeued[0].attempt_count == 1
                    assert result.requeued[0].claimed_by is None
                    assert result.requeued[0].lease_until is None

                # 5. 第二次推进：再次 CLAIMED
                with Session(engine, expire_on_commit=False) as session:
                    queue_repo = SqlAlchemyQueueRepository(session)
                    enqueued_again, claimed_again = advance_queue(
                        queue_repo, now, "worker-1", lease_seconds=60
                    )
                    session.commit()

                    assert enqueued_again == []
                    assert claimed_again is not None
                    assert claimed_again.id == queue_id
                    assert claimed_again.state == QueueState.CLAIMED
                    assert claimed_again.claimed_by == "worker-1"
                    assert claimed_again.lease_until == now + timedelta(seconds=60)

                # 6. 完成出队：QueueItem=COMPLETED、DramaTask=COMPLETED、台账落库
                with Session(engine, expire_on_commit=False) as session:
                    queue_repo = SqlAlchemyQueueRepository(session)
                    task_repo = SqlAlchemyTaskRepository(session)
                    ledger_repo = SqlAlchemyLedgerRepository(session)
                    ledger = complete_task(
                        queue_id,
                        "worker-1",
                        queue_repo,
                        task_repo,
                        ledger_repo,
                    )
                    session.commit()

                    assert ledger.id
                    assert ledger.task_id == task_id
                    assert ledger.final_status == "COMPLETED"
                    assert ledger.completed_at is not None

                # 7. 最终状态：活动队列清空，台账仍在
                with Session(engine) as session:
                    queue_repo = SqlAlchemyQueueRepository(session)
                    task_repo = SqlAlchemyTaskRepository(session)
                    ledger_repo = SqlAlchemyLedgerRepository(session)

                    assert queue_repo.list_by_state(QueueState.QUEUED) == []
                    assert queue_repo.list_by_state(QueueState.CLAIMED) == []
                    completed = queue_repo.list_by_state(QueueState.COMPLETED)
                    assert [item.id for item in completed] == [queue_id]

                    task = task_repo.get(task_id)
                    assert task is not None
                    assert task.status == TaskStatus.COMPLETED
                    assert len(ledger_repo.list_by_task(task_id)) == 1
            finally:
                engine.dispose()

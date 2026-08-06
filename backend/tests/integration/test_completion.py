"""complete_task 集成测试 —— 临时 SQLite + Alembic."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.completion_service import complete_task
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


class TestCompleteTaskIntegration:
    """complete_task 端到端集成测试."""

    def test_complete_task_from_claimed(self):
        """从 CLAIMED 状态完成出队，验证状态迁移与台账写入."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                queue_id = str(uuid.uuid4())

                # 插入 DramaTask + CLAIMED QueueItem
                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, "
                            "available_time, status) "
                            "VALUES (:tid, 'test-drama', 'TOMATO', :at, :status)"
                        ),
                        {"tid": task_id, "at": now, "status": TaskStatus.RUNNING},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at, claimed_by, lease_until) "
                            "VALUES (:qid, :tid, :state, 0, :at, 'worker-1', :lease)"
                        ),
                        {
                            "qid": queue_id,
                            "tid": task_id,
                            "state": QueueState.CLAIMED,
                            "at": now,
                            "lease": "2026-08-06T13:00:00",
                        },
                    )

                # 执行 complete_task
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
                        {
                            "album_id": "alb-123",
                            "product_id": "prod-456",
                            "task_name": "my-task",
                            "rule_version": "v1",
                            "config_version": "cfg1",
                        },
                    )
                    session.commit()
                    assert ledger.id, "台账应生成 id"
                    assert ledger.task_id == task_id
                    assert ledger.drama_name == "test-drama"
                    assert ledger.platform == "TOMATO"
                    assert ledger.final_status == "COMPLETED"
                    assert ledger.completed_at is not None
                    assert ledger.album_id == "alb-123"
                    assert ledger.product_id == "prod-456"
                    assert ledger.task_name == "my-task"

                # 验证数据库状态
                with Session(engine) as s:
                    # queue_item
                    qi = s.execute(
                        sa_text(
                            "SELECT state FROM queue_item WHERE id=:qid"
                        ),
                        {"qid": queue_id},
                    ).fetchone()
                    assert qi is not None
                    assert qi[0] == QueueState.COMPLETED

                    # drama_task
                    dt = s.execute(
                        sa_text(
                            "SELECT status FROM drama_task WHERE id=:tid"
                        ),
                        {"tid": task_id},
                    ).fetchone()
                    assert dt is not None
                    assert dt[0] == TaskStatus.COMPLETED

                    # task_ledger
                    tl = s.execute(
                        sa_text(
                            "SELECT task_id, drama_name, final_status "
                            "FROM task_ledger WHERE task_id=:tid"
                        ),
                        {"tid": task_id},
                    ).fetchone()
                    assert tl is not None
                    assert tl[0] == task_id
                    assert tl[1] == "test-drama"
                    assert tl[2] == "COMPLETED"

                    # 活动队列中不再包含该项
                    queued = s.execute(
                        sa_text(
                            "SELECT id FROM queue_item WHERE state=:state"
                        ),
                        {"state": QueueState.QUEUED},
                    ).fetchall()
                    assert all(r[0] != queue_id for r in queued), (
                        "QUEUED 列表不应包含已完成项"
                    )

                    claimed = s.execute(
                        sa_text(
                            "SELECT id FROM queue_item WHERE state=:state"
                        ),
                        {"state": QueueState.CLAIMED},
                    ).fetchall()
                    assert all(r[0] != queue_id for r in claimed), (
                        "CLAIMED 列表不应包含已完成项"
                    )
            finally:
                engine.dispose()

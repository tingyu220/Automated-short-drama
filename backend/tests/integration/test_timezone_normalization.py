"""时区归一化集成测试：东八区投放时间在 UTC 语义下到点可领取。"""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.queue_cycle import advance_queue
from backend.domain.queue.queue_item import QueueState
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)

SHANGHAI_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc


def _setup_temp_db(db_url: str):
    """创建临时数据库并运行 Alembic 迁移至 head."""
    engine = create_app_engine(db_url)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(Path("alembic").resolve()))
    command.upgrade(alembic_cfg, "head")
    return engine


class TestTimezoneNormalization:
    """东八区任务按 UTC 到点入队并领取。"""

    def test_cross_timezone_release_claimable_at_utc(self):
        """本地 00:30 的任务在 UTC 16:30 到点，未到点不可领取。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                release_local = datetime(2026, 8, 8, 0, 30, tzinfo=SHANGHAI_TZ)
                release_utc = release_local.astimezone(UTC)
                task_id = str(uuid.uuid4())
                queue_id = str(uuid.uuid4())

                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, "
                            "available_time) VALUES (:tid, '剧H', 'TOMATO', :at)"
                        ),
                        {"tid": task_id, "at": release_utc},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at) VALUES (:qid, :tid, :state, 0, :at)"
                        ),
                        {
                            "qid": queue_id,
                            "tid": task_id,
                            "state": QueueState.WAITING_TIME,
                            "at": release_utc,
                        },
                    )

                with Session(engine, expire_on_commit=False) as session:
                    repo = SqlAlchemyQueueRepository(session)
                    before, claimed_before = advance_queue(
                        repo,
                        release_utc - timedelta(minutes=1),
                        "worker-1",
                        lease_seconds=60,
                    )
                    session.commit()
                    assert before == []
                    assert claimed_before is None

                    at_release, claimed = advance_queue(
                        repo,
                        release_utc,
                        "worker-1",
                        lease_seconds=60,
                    )
                    session.commit()

                    assert [item.id for item in at_release] == [queue_id]
                    assert claimed is not None
                    assert claimed.id == queue_id
                    assert claimed.state == QueueState.CLAIMED
                    assert claimed.claimed_by == "worker-1"
            finally:
                engine.dispose()

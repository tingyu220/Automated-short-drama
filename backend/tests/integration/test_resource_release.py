"""resource_release_service 集成测试 —— 临时 SQLite + Alembic."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.resource_release_service import (
    BrowserSession,
    ResourceReleaseService,
)
from backend.domain.queue.queue_item import QueueState
from backend.domain.worker.worker_lease import STATUS_RUNNING, STATUS_STOPPED
from backend.infrastructure.database.engine import create_app_engine


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


class FakeBrowser(BrowserSession):
    """记录 close 调用次数的 fake 浏览器。"""

    def __init__(self, last_active: datetime) -> None:
        self.last_active = last_active
        self.closed = False

    def close(self) -> None:
        self.closed = True


class TestResourceReleaseIntegration:
    """release_after_completion 端到端集成测试。"""

    def test_release_after_completion(self):
        """完成后队列项 COMPLETED、租约 STOPPED、台账存在、浏览器已关闭。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                task_id = str(uuid.uuid4())
                queue_id = str(uuid.uuid4())
                worker_id = "worker-1"

                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, "
                            "available_time, status) "
                            "VALUES (:tid, 'test-drama', 'TOMATO', :at, :status)"
                        ),
                        {"tid": task_id, "at": now, "status": "RUNNING"},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at, claimed_by, lease_until) "
                            "VALUES (:qid, :tid, :state, 0, :at, :wid, :lease)"
                        ),
                        {
                            "qid": queue_id,
                            "tid": task_id,
                            "state": QueueState.CLAIMED,
                            "at": now,
                            "wid": worker_id,
                            "lease": "2026-08-06T13:00:00",
                        },
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO worker_lease (worker_id, host, pid, status, "
                            "heartbeat_at, lease_until) "
                            "VALUES (:wid, 'localhost', 100, :status, :hb, :lu)"
                        ),
                        {
                            "wid": worker_id,
                            "status": STATUS_RUNNING,
                            "hb": now,
                            "lu": "2026-08-06T13:00:00",
                        },
                    )

                browser = FakeBrowser(now)
                with Session(engine, expire_on_commit=False) as session:
                    service = ResourceReleaseService()
                    ledger = service.release_after_completion(
                        session,
                        queue_id,
                        worker_id,
                        {
                            "album_id": "alb-123",
                            "product_id": "prod-456",
                            "task_name": "my-task",
                        },
                        browser_session=browser,
                    )
                    session.commit()

                    assert ledger.id, "台账应生成 id"
                    assert ledger.task_id == task_id
                    assert ledger.final_status == "COMPLETED"
                    assert ledger.album_id == "alb-123"
                    assert browser.closed is True

                with Session(engine) as s:
                    qi = s.execute(
                        sa_text("SELECT state FROM queue_item WHERE id=:qid"),
                        {"qid": queue_id},
                    ).fetchone()
                    assert qi is not None
                    assert qi[0] == QueueState.COMPLETED

                    wl = s.execute(
                        sa_text(
                            "SELECT status FROM worker_lease WHERE worker_id=:wid"
                        ),
                        {"wid": worker_id},
                    ).fetchone()
                    assert wl is not None
                    assert wl[0] == STATUS_STOPPED

                    tl = s.execute(
                        sa_text(
                            "SELECT task_id, final_status FROM task_ledger "
                            "WHERE task_id=:tid"
                        ),
                        {"tid": task_id},
                    ).fetchone()
                    assert tl is not None
                    assert tl[0] == task_id
                    assert tl[1] == "COMPLETED"
            finally:
                engine.dispose()

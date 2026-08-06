"""claim_next 并发/顺序原子性集成测试 —— 临时 SQLite + Alembic."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.claim_service import claim_next_task
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.domain.queue.queue_item import QueueState
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


class TestClaimConcurrency:
    """验证原子领取：两个 session 顺序调用，恰好一个成功."""

    def test_two_sessions_one_wins(self):
        """插入 1 条 QUEUED，两个 session 顺序 claim，恰好一个成功."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                # 插入 1 条 QUEUED 数据
                now = datetime(2026, 8, 6, 12, 0, 0)
                qid = str(uuid.uuid4())
                tid = str(uuid.uuid4())
                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, available_time) "
                            "VALUES (:tid, 'test-drama', 'test', :at)"
                        ),
                        {"tid": tid, "at": now},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, available_at) "
                            "VALUES (:qid, :tid, 'QUEUED', 0, :at)"
                        ),
                        {"qid": qid, "tid": tid, "at": now},
                    )

                # 两个独立 session
                s1 = Session(engine, expire_on_commit=False)
                s2 = Session(engine, expire_on_commit=False)
                try:
                    # 第一次领取 —— 应成功
                    item1 = claim_next_task(
                        SqlAlchemyQueueRepository(s1),
                        "worker-A",
                        lease_seconds=60,
                    )
                    s1.commit()
                    assert item1 is not None, "第一个 session 应成功领取"
                    assert item1.id == qid
                    assert item1.state == QueueState.CLAIMED
                    assert item1.claimed_by == "worker-A"
                    assert item1.lease_until is not None

                    # 第二次领取 —— 应返回 None（已被领走）
                    item2 = claim_next_task(
                        SqlAlchemyQueueRepository(s2),
                        "worker-B",
                        lease_seconds=60,
                    )
                    s2.commit()
                    assert item2 is None, "第二个 session 应返回 None"
                finally:
                    s1.close()
                    s2.close()

                # 验证数据库中状态正确
                with Session(engine) as s:
                    row = s.execute(
                        sa_text(
                            "SELECT state, claimed_by, lease_until FROM queue_item WHERE id=:qid"
                        ),
                        {"qid": qid},
                    ).fetchone()
                    assert row is not None
                    assert row[0] == QueueState.CLAIMED
                    assert row[1] == "worker-A"
                    assert row[2] is not None
            finally:
                engine.dispose()

    def test_no_queued_items_returns_none(self):
        """无 QUEUED 项时 claim_next 返回 None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                with Session(engine) as s:
                    result = claim_next_task(
                        SqlAlchemyQueueRepository(s), "worker-X"
                    )
                    s.commit()
                    assert result is None
            finally:
                engine.dispose()

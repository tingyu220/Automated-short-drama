"""recover_expired 集成测试 —— 临时 SQLite + Alembic."""
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

from backend.application.services.recovery_service import recover_expired
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


class TestRecoveryIntegration:
    """验证崩溃恢复在真实 SQLite 中的行为."""

    def test_expired_claimed_requeued_non_expired_untouched(self):
        """插入过期 CLAIMED 与未过期 CLAIMED，恢复后只有过期项被 requeue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                tid1 = str(uuid.uuid4())
                qid1 = str(uuid.uuid4())  # 过期
                qid2 = str(uuid.uuid4())  # 未过期

                with engine.begin() as conn:
                    # 插入关联的 drama_task
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, available_time) "
                            "VALUES (:tid, 'test', 'test', :at)"
                        ),
                        {"tid": tid1, "at": now},
                    )
                    # 过期 CLAIMED
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at, claimed_by, lease_until, attempt_count) "
                            "VALUES (:qid, :tid, 'CLAIMED', 0, :at, 'worker-1', :lease, 0)"
                        ),
                        {
                            "qid": qid1,
                            "tid": tid1,
                            "at": now,
                            "lease": now - timedelta(seconds=10),
                        },
                    )
                    # 未过期 CLAIMED
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at, claimed_by, lease_until, attempt_count) "
                            "VALUES (:qid, :tid, 'CLAIMED', 0, :at, 'worker-2', :lease, 0)"
                        ),
                        {
                            "qid": qid2,
                            "tid": tid1,
                            "at": now,
                            "lease": now + timedelta(seconds=10),
                        },
                    )

                with Session(engine) as s:
                    result = recover_expired(s, now)
                    s.commit()

                # 验证：过期项被 requeue，未过期项不动
                assert len(result.requeued) == 1
                assert len(result.manual_review) == 0
                assert result.requeued[0].id == qid1
                assert result.requeued[0].state == QueueState.QUEUED
                assert result.requeued[0].claimed_by is None
                assert result.requeued[0].lease_until is None
                assert result.requeued[0].attempt_count == 1

                with Session(engine) as s:
                    row2 = s.execute(
                        sa_text(
                            "SELECT state, claimed_by FROM queue_item WHERE id=:qid"
                        ),
                        {"qid": qid2},
                    ).fetchone()
                    assert row2 is not None
                    assert row2[0] == QueueState.CLAIMED
                    assert row2[1] == "worker-2"

            finally:
                engine.dispose()

    def test_expired_max_attempts_to_manual_review(self):
        """attempt_count=max 的过期项恢复后进入 MANUAL_REVIEW."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                tid = str(uuid.uuid4())
                qid = str(uuid.uuid4())

                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, available_time) "
                            "VALUES (:tid, 'test', 'test', :at)"
                        ),
                        {"tid": tid, "at": now},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at, claimed_by, lease_until, attempt_count) "
                            "VALUES (:qid, :tid, 'RUNNING', 0, :at, 'worker-1', :lease, 3)"
                        ),
                        {
                            "qid": qid,
                            "tid": tid,
                            "at": now,
                            "lease": now - timedelta(seconds=10),
                        },
                    )

                with Session(engine) as s:
                    result = recover_expired(s, now)
                    s.commit()

                assert len(result.requeued) == 0
                assert len(result.manual_review) == 1
                assert result.manual_review[0].id == qid
                assert result.manual_review[0].state == QueueState.MANUAL_REVIEW
                assert result.manual_review[0].claimed_by is None
                assert result.manual_review[0].lease_until is None
                assert result.manual_review[0].attempt_count == 4
            finally:
                engine.dispose()

    def test_no_expired_items_empty_result(self):
        """无过期项时返回空结果."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                tid = str(uuid.uuid4())
                qid = str(uuid.uuid4())

                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task (id, drama_name, platform, available_time) "
                            "VALUES (:tid, 'test', 'test', :at)"
                        ),
                        {"tid": tid, "at": now},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO queue_item (id, task_id, state, priority, "
                            "available_at, claimed_by, lease_until, attempt_count) "
                            "VALUES (:qid, :tid, 'CLAIMED', 0, :at, 'worker-1', :lease, 0)"
                        ),
                        {
                            "qid": qid,
                            "tid": tid,
                            "at": now,
                            "lease": now + timedelta(seconds=60),
                        },
                    )

                with Session(engine) as s:
                    result = recover_expired(s, now)
                    s.commit()

                assert len(result.requeued) == 0
                assert len(result.manual_review) == 0
            finally:
                engine.dispose()

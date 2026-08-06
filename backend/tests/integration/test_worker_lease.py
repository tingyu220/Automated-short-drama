"""Worker 租约集成测试，使用临时 SQLite + Alembic."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text

from backend.application.services.worker_heartbeat import (
    acquire_lease,
    heartbeat,
    release_lease,
    is_lease_active,
    list_expired_leases,
)
from backend.domain.worker.worker_lease import STATUS_RUNNING, STATUS_STOPPED
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.worker_lease_repository import (
    SqlAlchemyWorkerLeaseRepository,
)


def _setup_temp_db(db_url: str):
    engine = create_app_engine(db_url)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(Path("alembic").resolve()))
    command.upgrade(alembic_cfg, "head")
    return engine


class TestWorkerLeaseTable:

    def test_table_exists_after_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                with engine.connect() as conn:
                    row = conn.exec_driver_sql(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='worker_lease'"
                    ).fetchone()
                assert row is not None, "worker_lease 表应存在"
            finally:
                engine.dispose()

    def test_unique_worker_id_constraint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                now = datetime(2026, 8, 6, 12, 0, 0)
                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO worker_lease (worker_id, host, pid, status, heartbeat_at, lease_until) "
                            "VALUES (:wid, :host, :pid, :status, :hb, :lu)"
                        ),
                        {
                            "wid": "worker-1",
                            "host": "localhost",
                            "pid": 100,
                            "status": "RUNNING",
                            "hb": now,
                            "lu": now + timedelta(seconds=60),
                        },
                    )
                with pytest.raises(Exception):
                    with engine.begin() as conn:
                        conn.execute(
                            sa_text(
                                "INSERT INTO worker_lease (worker_id, host, pid, status, heartbeat_at, lease_until) "
                                "VALUES (:wid, :host, :pid, :status, :hb, :lu)"
                            ),
                            {
                                "wid": "worker-1",
                                "host": "other-host",
                                "pid": 200,
                                "status": "RUNNING",
                                "hb": now,
                                "lu": now + timedelta(seconds=60),
                            },
                        )
            finally:
                engine.dispose()


class TestWorkerHeartbeatIntegration:

    def test_acquire_and_heartbeat_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                from sqlalchemy.orm import Session
                session = Session(engine)
                try:
                    ok = acquire_lease(
                        SqlAlchemyWorkerLeaseRepository(session),
                        "w1",
                        "host1",
                        100,
                        60,
                    )
                    assert ok is True, "首次获取租约应成功"
                    session.commit()
                    assert is_lease_active(
                        SqlAlchemyWorkerLeaseRepository(session), "w1"
                    ) is True
                    result = heartbeat(
                        SqlAlchemyWorkerLeaseRepository(session),
                        "w1",
                        "host1",
                        100,
                        60,
                    )
                    assert result.worker_id == "w1"
                    assert result.status == STATUS_RUNNING
                    session.commit()
                    assert release_lease(
                        SqlAlchemyWorkerLeaseRepository(session), "w1"
                    ) is True
                    session.commit()
                    assert is_lease_active(
                        SqlAlchemyWorkerLeaseRepository(session), "w1"
                    ) is False
                finally:
                    session.close()
            finally:
                engine.dispose()

    def test_acquire_rejected_by_other_active_worker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                from sqlalchemy.orm import Session
                s1 = Session(engine)
                s2 = Session(engine)
                try:
                    assert acquire_lease(
                        SqlAlchemyWorkerLeaseRepository(s1),
                        "w1",
                        "host1",
                        100,
                        60,
                    ) is True
                    s1.commit()
                    assert acquire_lease(
                        SqlAlchemyWorkerLeaseRepository(s2),
                        "w2",
                        "host2",
                        200,
                        60,
                    ) is False
                finally:
                    s1.close()
                    s2.close()
            finally:
                engine.dispose()

    def test_upsert_overwrites_same_worker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                from sqlalchemy.orm import Session
                session = Session(engine)
                try:
                    r1 = heartbeat(
                        SqlAlchemyWorkerLeaseRepository(session),
                        "w1",
                        "host1",
                        100,
                        60,
                    )
                    session.commit()
                    r2 = heartbeat(
                        SqlAlchemyWorkerLeaseRepository(session),
                        "w1",
                        "hostA",
                        999,
                        120,
                    )
                    session.commit()
                    rows = session.execute(
                        sa_text("SELECT count(*) FROM worker_lease WHERE worker_id='w1'")
                    ).scalar()
                    assert rows == 1
                    assert r2.host == "hostA"
                    assert r2.pid == 999
                finally:
                    session.close()
            finally:
                engine.dispose()

    def test_list_expired_leases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                from sqlalchemy.orm import Session
                session = Session(engine)
                try:
                    now = datetime(2026, 8, 6, 12, 0, 0)
                    session.execute(
                        sa_text(
                            "INSERT INTO worker_lease (worker_id, host, pid, status, heartbeat_at, lease_until) "
                            "VALUES (:wid, :host, :pid, :status, :hb, :lu)"
                        ),
                        {
                            "wid": "expired-1",
                            "host": "h1",
                            "pid": 1,
                            "status": "RUNNING",
                            "hb": now - timedelta(seconds=120),
                            "lu": now - timedelta(seconds=10),
                        },
                    )
                    session.commit()
                    expired = list_expired_leases(
                        SqlAlchemyWorkerLeaseRepository(session), now=now
                    )
                    assert len(expired) == 1
                    assert expired[0].worker_id == "expired-1"
                finally:
                    session.close()
            finally:
                engine.dispose()

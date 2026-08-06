"""resource_cleanup_service 单元测试."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.application.services.resource_cleanup_service import (
    ResourceCleanupService,
    RetentionConfig,
)
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.execution import (
    ExecutionArtifactRecord,
)
from backend.infrastructure.database.models.task import DramaTaskRecord


@pytest.fixture(autouse=True)
def _reenable_service_logger():
    """Alembic fileConfig 会禁用既有 logger，测试前恢复服务 logger。"""
    service_logger = logging.getLogger(
        "backend.application.services.resource_cleanup_service"
    )
    service_logger.disabled = False
    yield


@pytest.fixture
def db_session():
    """内存 SQLite + 全量表结构，返回 (session, task_id)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    task_id = str(uuid.uuid4())
    session.add(
        DramaTaskRecord(
            id=task_id,
            drama_name="test-drama",
            platform="TOMATO",
            available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
    )
    session.commit()
    yield session, task_id
    session.close()
    engine.dispose()


def _add_artifact(
    session: Session,
    task_id: str,
    path: str,
    created_at: datetime,
) -> None:
    session.add(
        ExecutionArtifactRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            artifact_type="SCREENSHOT",
            path=path,
            size_bytes=1,
            created_at=created_at,
        )
    )
    session.flush()


def _artifact_count(session: Session) -> int:
    return session.execute(
        select(func.count(ExecutionArtifactRecord.id))
    ).scalar_one()


def _set_mtime(path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


class TestRetentionConfig:
    """RetentionConfig 默认值."""

    def test_defaults(self):
        cfg = RetentionConfig()
        assert cfg.log_retention_days == 30
        assert cfg.artifact_retention_days == 30
        assert cfg.temp_max_age_hours == 24
        assert cfg.max_artifacts_per_task == 50


class TestCleanupExpiredArtifacts:
    """过期产物清理."""

    def test_deletes_expired_rows_and_files(self, tmp_path, db_session):
        session, task_id = db_session
        root = tmp_path / "artifacts"
        root.mkdir()
        old_file = root / "old.png"
        old_file.write_bytes(b"old")
        fresh_file = root / "fresh.png"
        fresh_file.write_bytes(b"fresh")
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _add_artifact(session, task_id, str(old_file), now - timedelta(days=31))
        _add_artifact(session, task_id, str(fresh_file), now - timedelta(days=1))

        service = ResourceCleanupService(artifacts_root=root)
        deleted = service.cleanup_expired_artifacts(session, now, retention_days=30)
        session.commit()

        assert deleted == 1
        assert not old_file.exists()
        assert fresh_file.exists()
        assert _artifact_count(session) == 1

    def test_uses_config_default_retention(self, tmp_path, db_session):
        session, task_id = db_session
        root = tmp_path / "artifacts"
        root.mkdir()
        old_file = root / "old.png"
        old_file.write_bytes(b"old")
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _add_artifact(session, task_id, str(old_file), now - timedelta(days=2))

        service = ResourceCleanupService(
            artifacts_root=root,
            config=RetentionConfig(artifact_retention_days=1),
        )
        deleted = service.cleanup_expired_artifacts(session, now)
        session.commit()

        assert deleted == 1
        assert not old_file.exists()

    def test_out_of_bounds_physical_file_skipped(self, tmp_path, db_session, caplog):
        session, task_id = db_session
        root = tmp_path / "artifacts"
        root.mkdir()
        outside_file = tmp_path / "outside.txt"
        outside_file.write_bytes(b"keep")
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _add_artifact(session, task_id, "../outside.txt", now - timedelta(days=31))

        service = ResourceCleanupService(artifacts_root=root)
        with caplog.at_level(logging.WARNING):
            deleted = service.cleanup_expired_artifacts(session, now)
        session.commit()

        assert deleted == 1
        assert outside_file.exists()
        assert _artifact_count(session) == 0
        assert any("跳过" in record.message for record in caplog.records)

    def test_root_itself_never_deleted(self, tmp_path, db_session, caplog):
        session, task_id = db_session
        root = tmp_path / "artifacts"
        root.mkdir()
        inner_file = root / "keep.txt"
        inner_file.write_bytes(b"keep")
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _add_artifact(session, task_id, ".", now - timedelta(days=31))

        service = ResourceCleanupService(artifacts_root=root)
        with caplog.at_level(logging.WARNING):
            deleted = service.cleanup_expired_artifacts(session, now)
        session.commit()

        assert deleted == 1
        assert root.exists()
        assert inner_file.exists()
        assert any("跳过" in record.message for record in caplog.records)


class TestCleanupLogsAndTemp:
    """日志与临时文件按 mtime 清理."""

    def test_cleanup_expired_logs_by_mtime(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        old_log = log_dir / "old.log"
        old_log.write_text("old")
        fresh_log = log_dir / "fresh.log"
        fresh_log.write_text("fresh")
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _set_mtime(old_log, now - timedelta(days=31))
        _set_mtime(fresh_log, now - timedelta(days=1))

        service = ResourceCleanupService(artifacts_root=tmp_path / "artifacts")
        deleted = service.cleanup_expired_logs(log_dir, now, retention_days=30)

        assert deleted == 1
        assert not old_log.exists()
        assert fresh_log.exists()

    def test_cleanup_temp_files_and_dirs_by_mtime(self, tmp_path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        old_file = temp_dir / "old.tmp"
        old_file.write_bytes(b"old")
        old_dir = temp_dir / "old_dir"
        old_dir.mkdir()
        (old_dir / "inner.tmp").write_bytes(b"inner")
        fresh_file = temp_dir / "fresh.tmp"
        fresh_file.write_bytes(b"fresh")
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _set_mtime(old_file, now - timedelta(hours=25))
        _set_mtime(old_dir, now - timedelta(hours=25))
        _set_mtime(fresh_file, now - timedelta(hours=1))

        service = ResourceCleanupService(artifacts_root=tmp_path / "artifacts")
        deleted = service.cleanup_temp_files(temp_dir, now, max_age_hours=24)

        assert deleted == 2
        assert not old_file.exists()
        assert not old_dir.exists()
        assert fresh_file.exists()

    def test_cleanup_expired_logs_normalizes_naive_now(self, tmp_path):
        """naive now 应按 UTC 归一化后与 aware mtime 比较。"""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        old_log = log_dir / "old.log"
        old_log.write_text("old")
        aware_now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        _set_mtime(old_log, aware_now - timedelta(days=31))

        service = ResourceCleanupService(artifacts_root=tmp_path / "artifacts")
        deleted = service.cleanup_expired_logs(
            log_dir,
            datetime(2026, 8, 6, 12, 0, 0),
            retention_days=30,
        )

        assert deleted == 1
        assert not old_log.exists()


class TestEnforceArtifactLimit:
    """按任务保留最新 N 条产物."""

    def test_keeps_latest_and_deletes_older(self, tmp_path, db_session):
        session, task_id = db_session
        root = tmp_path / "artifacts"
        root.mkdir()
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        files: list[Path] = []
        for index in range(5):
            path = root / f"artifact-{index}.png"
            path.write_bytes(b"data")
            files.append(path)
            _add_artifact(
                session,
                task_id,
                str(path),
                now - timedelta(days=10 - index),
            )

        service = ResourceCleanupService(artifacts_root=root)
        deleted = service.enforce_artifact_limit(session, task_id, max_count=2)
        session.commit()

        assert deleted == 3
        assert not files[0].exists()
        assert not files[1].exists()
        assert not files[2].exists()
        assert files[3].exists()
        assert files[4].exists()
        assert _artifact_count(session) == 2

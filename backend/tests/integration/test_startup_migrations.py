"""启动迁移集成测试：run_migrations + automation_worker --once."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database import migrations as migrations_module
from backend.infrastructure.database.migrations import run_migrations


def _table_exists(engine, table_name: str) -> bool:
    """检查 SQLite 中指定表是否存在."""
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None


class TestRunMigrations:
    """run_migrations 函数单元测试."""

    def test_migration_creates_worker_lease_table(self):
        """全新临时 SQLite DB 调用 run_migrations 后存在 worker_lease 表."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"

            run_migrations(db_url)

            engine = create_app_engine(db_url)
            try:
                assert _table_exists(engine, "worker_lease"), (
                    "worker_lease 表应存在"
                )
            finally:
                engine.dispose()

    def test_migration_idempotent(self):
        """再次调用 run_migrations 不报错（幂等）."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            backup_dir = Path(tmpdir) / "data" / "backups"

            run_migrations(db_url)
            # 第二次调用应不报错
            run_migrations(db_url, backup_dir=backup_dir)

            engine = create_app_engine(db_url)
            try:
                assert _table_exists(engine, "worker_lease"), (
                    "幂等迁移后 worker_lease 表应仍然存在"
                )
            finally:
                engine.dispose()

    def test_migration_creates_backup_before_upgrade(self, monkeypatch):
        """数据库文件存在时，迁移前先生成备份，迁移失败也不丢失备份。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            backup_dir = Path(tmpdir) / "backups"
            run_migrations(db_url)

            def _fail_upgrade(*args, **kwargs):
                raise RuntimeError("migration boom")

            monkeypatch.setattr(
                migrations_module.alembic.command,
                "upgrade",
                _fail_upgrade,
            )

            with pytest.raises(RuntimeError, match="migration boom"):
                run_migrations(db_url, backup_dir=backup_dir)

            backups = list(backup_dir.glob("app-*.db"))
            assert len(backups) == 1

    def test_migration_backup_failure_raises(self, monkeypatch):
        """迁移前备份失败时必须明确失败，不能静默继续。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            backup_dir = Path(tmpdir) / "backups"
            run_migrations(db_url)

            def _fail_backup(*args, **kwargs):
                raise RuntimeError("backup boom")

            monkeypatch.setattr(
                migrations_module,
                "backup_database",
                _fail_backup,
            )

            with pytest.raises(RuntimeError, match="backup boom"):
                run_migrations(db_url, backup_dir=backup_dir)


class TestAutomationWorkerOnce:
    """automation_worker --once 子进程测试."""

    def test_worker_once_exit_zero_on_fresh_db(self):
        """全新临时数据库上执行 worker --once 退出码为 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"

            env = {**os.environ, "WORKBUDDY_DATABASE_URL": db_url}
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.bootstrap.automation_worker",
                    "--once",
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            assert result.returncode == 0, (
                f"worker --once 应退出 0，实际 {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

"""SQLite 连接与 Alembic 集成测试."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text

from backend.domain.errors.domain_error import ConfigurationError
from backend.infrastructure.database.backup import backup_database
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.session import SessionLocal


def _get_pragma(engine, pragma_name: str) -> str:
    """读取 SQLite PRAGMA 当前值。"""
    with engine.connect() as conn:
        result = conn.exec_driver_sql(f"PRAGMA {pragma_name}")
        row = result.fetchone()
        return str(row[0]) if row else ""


def _table_exists(engine, table_name: str) -> bool:
    """检查 SQLite 中指定表是否存在。"""
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None


class TestEngine:
    """引擎创建与 PRAGMA 测试。"""

    def test_create_engine_with_temp_db(self):
        """使用临时目录 SQLite 文件创建引擎并确认 PRAGMA 设置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            eng = create_app_engine(db_url)
            try:
                with eng.connect():
                    pass
                assert _get_pragma(eng, "journal_mode") == "wal"
                assert _get_pragma(eng, "foreign_keys") == "1"
                assert _get_pragma(eng, "busy_timeout") == "5000"
            finally:
                eng.dispose()


class TestAlembic:
    """Alembic 迁移测试。"""

    def test_migrate_head_on_temp_db(self):
        """对临时 SQLite 执行 alembic upgrade head 应成功，并确认迁移作用于临时 DB。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"

            eng = create_app_engine(db_url)
            try:
                with eng.connect():
                    pass

                alembic_cfg = Config("alembic.ini")
                alembic_cfg.set_main_option("sqlalchemy.url", db_url)
                alembic_cfg.set_main_option(
                    "script_location",
                    str(Path("alembic").resolve()),
                )
                command.upgrade(alembic_cfg, "head")

                # 验证迁移真实作用于临时 DB：alembic_version 表应存在
                assert _table_exists(eng, "alembic_version"), (
                    "迁移未作用于临时 DB，alembic_version 表不存在"
                )
            finally:
                eng.dispose()


class TestBackup:
    """backup_database 测试。"""

    def test_backup_creates_timestamped_file(self):
        """备份在指定目录生成带时间戳的文件，内容与源一致。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "test.db"
            conn = sqlite3.connect(source)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.execute("INSERT INTO t VALUES (42)")
            conn.commit()
            conn.close()
            backup_dir = tmp / "data" / "backups"

            result = backup_database(source, backup_dir)

            assert result.exists()
            assert result.name.startswith("app-")
            assert result.name.endswith(".db")
            assert result.parent == backup_dir
            check = sqlite3.connect(result)
            try:
                assert check.execute("SELECT x FROM t").fetchall() == [(42,)]
            finally:
                check.close()

    def test_backup_does_not_overwrite_existing_backup(self):
        """同秒重复备份不会覆盖已有文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "test.db"
            conn = sqlite3.connect(source)
            conn.execute("CREATE TABLE t (x INTEGER)")
            conn.commit()
            conn.close()
            backup_dir = tmp / "backups"

            first = backup_database(source, backup_dir)
            second = backup_database(source, backup_dir)

            assert first != second
            assert first.exists() and second.exists()

    def test_backup_source_not_found_raises(self):
        """源文件不存在时抛出 ConfigurationError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "nonexistent.db"
            backup_dir = Path(tmpdir) / "backups"
            with pytest.raises(ConfigurationError):
                backup_database(source, backup_dir)


class TestSession:
    """数据库会话测试。"""

    def test_session_local_bind(self):
        """SessionLocal 可正常连接并执行查询。"""
        session = SessionLocal()
        try:
            session.execute(sa_text("SELECT 1"))
        finally:
            session.close()

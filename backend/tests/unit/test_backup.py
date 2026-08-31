"""SQLite 数据库备份单元测试."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.domain.errors.domain_error import ConfigurationError
from backend.infrastructure.database.backup import backup_database


def _create_test_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test (name) VALUES ('hello')")
    conn.commit()
    conn.close()


def test_backup_creates_valid_file(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_test_db(db_path)
    backup_dir = tmp_path / "backups"

    result = backup_database(db_path, backup_dir)

    assert result.exists()
    assert result.parent == backup_dir
    assert result.suffix == ".db"
    assert result.name.startswith("app-")


def test_backup_filename_uses_utc_timestamp_format(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_test_db(db_path)
    backup_dir = tmp_path / "backups"

    result = backup_database(db_path, backup_dir)

    pattern = r"^app-\d{8}-\d{6}-\d{6}\.db$"
    assert re.match(pattern, result.name), f"备份文件名格式不符: {result.name}"


def test_backup_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_test_db(db_path)
    backup_dir = tmp_path / "backups"

    result = backup_database(db_path, backup_dir)

    conn = sqlite3.connect(str(result))
    rows = conn.execute("SELECT name FROM test").fetchall()
    conn.close()
    assert rows == [("hello",)]


def test_backup_raises_on_missing_db(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    missing_db = tmp_path / "nonexistent.db"

    with pytest.raises(ConfigurationError, match="数据库文件不存在"):
        backup_database(missing_db, backup_dir)


def test_backup_unique_path_on_same_second(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_test_db(db_path)
    backup_dir = tmp_path / "backups"

    first = backup_database(db_path, backup_dir)
    second = backup_database(db_path, backup_dir)

    assert first != second
    assert first.exists()
    assert second.exists()

"""SQLite 数据库文件备份."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from backend.domain.errors.domain_error import ConfigurationError


def backup_database(db_path: Path, backup_dir: Path) -> Path:
    """用 SQLite 在线备份 API 生成一致性备份。

    Args:
        db_path: 源数据库文件路径。
        backup_dir: 备份目标目录。

    Returns:
        备份文件路径。

    Raises:
        ConfigurationError: 源文件不存在时。
    """
    if not db_path.exists():
        raise ConfigurationError(f"数据库文件不存在: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = _unique_backup_path(backup_dir, f"app-{timestamp}.db")
    source_conn = sqlite3.connect(str(db_path))
    target_conn = sqlite3.connect(str(backup_path))
    try:
        with source_conn:
            source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    return backup_path


def _unique_backup_path(backup_dir: Path, name: str) -> Path:
    """同秒重复备份时追加序号，避免覆盖已有备份。"""
    candidate = backup_dir / name
    counter = 1
    while candidate.exists():
        candidate = backup_dir / f"{Path(name).stem}-{counter}{Path(name).suffix}"
        counter += 1
    return candidate

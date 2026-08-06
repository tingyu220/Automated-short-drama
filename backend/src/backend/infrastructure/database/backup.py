"""SQLite 数据库文件备份."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from backend.domain.errors.domain_error import ConfigurationError


def backup_database(db_path: Path, backup_dir: Path) -> Path:
    """复制数据库文件到带时间戳的备份。

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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"app-{timestamp}.db"
    backup_path = backup_dir / backup_name
    shutil.copy2(db_path, backup_path)
    return backup_path

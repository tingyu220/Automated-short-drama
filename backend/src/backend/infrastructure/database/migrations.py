"""Alembic 迁移封装，供 Worker/Server 启动前调用.

用法:
    python -m backend.infrastructure.database.migrations          # 自动迁移
    run_migrations("sqlite:////path/to/db")                       # 代码调用
"""
from __future__ import annotations

import logging
from pathlib import Path

import alembic.command
import alembic.config

from backend.infrastructure.config.settings import PROJECT_ROOT, Settings
from backend.infrastructure.database.backup import backup_database
from backend.infrastructure.database.engine import resolve_sqlite_url

logger = logging.getLogger(__name__)

_ALEMBIC_INI = PROJECT_ROOT / "backend" / "alembic.ini"


def run_migrations(
    database_url: str | None = None,
    *,
    backup_dir: Path | None = None,
) -> None:
    """迁移前备份数据库，再执行 Alembic upgrade head.

    Args:
        database_url: 可选数据库连接串；默认使用 Settings.database_url.
        backup_dir: 可选备份目录；默认 data/backups.

    Raises:
        数据库文件存在但备份失败时，直接抛出备份异常，不静默继续迁移.
    """
    settings = Settings()
    effective_url = database_url or settings.database_url
    resolved_url = resolve_sqlite_url(effective_url)
    cfg = alembic.config.Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", resolved_url)

    db_path = _sqlite_path(resolved_url)
    if db_path is not None and db_path.exists():
        target = backup_dir or (settings.data_dir / "backups")
        backup_database(db_path, target)

    alembic.command.upgrade(cfg, "head")


def _sqlite_path(database_url: str) -> Path | None:
    """从 sqlite URL 提取数据库文件路径；非 SQLite 返回 None。"""
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url[len("sqlite:///") :])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("执行数据库迁移...")
    run_migrations()
    logger.info("数据库迁移完成.")

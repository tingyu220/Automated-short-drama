"""Alembic 迁移封装，供 Worker/Server 启动前调用.

用法:
    python -m backend.infrastructure.database.migrations          # 自动迁移
    run_migrations("sqlite:////path/to/db")                       # 代码调用
"""
from __future__ import annotations

import logging

import alembic.command
import alembic.config

from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import resolve_sqlite_url

logger = logging.getLogger(__name__)

_ALEMBIC_INI = PROJECT_ROOT / "backend" / "alembic.ini"


def run_migrations(database_url: str | None = None) -> None:
    """执行 Alembic upgrade head，幂等安全.

    Args:
        database_url: 可选数据库连接串；默认使用 Settings.database_url.
    """
    cfg = alembic.config.Config(str(_ALEMBIC_INI))

    if database_url is not None:
        cfg.set_main_option("sqlalchemy.url", resolve_sqlite_url(database_url))

    alembic.command.upgrade(cfg, "head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("执行数据库迁移...")
    run_migrations()
    logger.info("数据库迁移完成.")

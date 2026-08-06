"""Alembic 环境配置，运行时从 config 或 Settings 注入 database_url。"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.engine import resolve_sqlite_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_database_url() -> str:
    """获取 database_url：优先 config 注入，未设置时回退 Settings 默认。"""
    url = config.get_main_option("sqlalchemy.url")
    if url and url != "placeholder":
        return resolve_sqlite_url(url)
    return resolve_sqlite_url(Settings().database_url)


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本。"""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接连接数据库执行迁移。"""
    url = _get_database_url()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

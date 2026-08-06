"""SQLite 引擎创建与 PRAGMA 配置."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, event, create_engine

from backend.infrastructure.config.settings import Settings, PROJECT_ROOT


def _resolve_sqlite_url(database_url: str) -> str:
    """将 SQLite 相对路径解析为绝对路径。"""
    if not database_url.startswith("sqlite:///"):
        return database_url
    prefix = "sqlite:///"
    rel_path = database_url[len(prefix):]
    if rel_path.startswith("/"):
        return database_url
    abs_path = (PROJECT_ROOT / rel_path).resolve()
    return f"sqlite:///{abs_path}"


def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    """在每次新连接时设置 SQLite PRAGMA。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_app_engine(database_url: str | None = None) -> Engine:
    """创建 SQLAlchemy Engine。

    Args:
        database_url: 数据库连接串；默认使用 Settings.database_url。

    对 SQLite 自动设置 check_same_thread=False、WAL 模式、外键约束与 busy_timeout。
    """
    if database_url is None:
        database_url = Settings().database_url

    url = _resolve_sqlite_url(database_url)
    db_path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else None
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    connect_args = {}
    if "sqlite" in url:
        connect_args["check_same_thread"] = False

    engine = create_engine(url, connect_args=connect_args)

    if "sqlite" in url:
        event.listen(engine, "connect", _set_sqlite_pragmas)

    return engine


engine = create_app_engine()

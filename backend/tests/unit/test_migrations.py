"""从仓库根目录调用迁移时的路径契约。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from backend.infrastructure.database.migrations import _ALEMBIC_INI, run_migrations


def test_migration_config_points_to_backend_alembic_directory() -> None:
    """防止 Worker 从根目录启动时把 script_location 解析到错误位置。"""
    assert _ALEMBIC_INI.parent.joinpath("alembic").is_dir()


def test_run_migrations_works_from_repository_root() -> None:
    """防止真实启动无法加载迁移脚本。"""
    with tempfile.TemporaryDirectory() as tmp:
        run_migrations(f"sqlite:///{Path(tmp) / 'root.db'}")

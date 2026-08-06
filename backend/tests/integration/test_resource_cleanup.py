"""资源清理服务集成测试 —— 临时 SQLite + Alembic + 真实文件."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.resource_cleanup_service import (
    ResourceCleanupService,
)
from backend.infrastructure.database.engine import create_app_engine


def _setup_temp_db(db_url: str):
    """创建临时数据库并运行 Alembic 迁移至 head."""
    engine = create_app_engine(db_url)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option(
        "script_location", str(Path("alembic").resolve())
    )
    command.upgrade(alembic_cfg, "head")
    return engine


class TestResourceCleanupIntegration:
    """验证清理在真实 SQLite + 文件系统中的行为."""

    def test_cleanup_expired_artifacts_with_real_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            db_path = base / "test.db"
            db_url = f"sqlite:///{db_path}"
            engine = _setup_temp_db(db_url)
            try:
                artifacts_root = base / "artifacts"
                artifacts_root.mkdir()
                now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
                task_id = str(uuid.uuid4())

                expired_file = artifacts_root / "expired.png"
                expired_file.write_bytes(b"expired")
                fresh_file = artifacts_root / "fresh.png"
                fresh_file.write_bytes(b"fresh")
                outside_file = base / "outside.txt"
                outside_file.write_bytes(b"outside")

                with engine.begin() as conn:
                    conn.execute(
                        sa_text(
                            "INSERT INTO drama_task "
                            "(id, drama_name, platform, available_time) "
                            "VALUES (:tid, 'test', 'test', :at)"
                        ),
                        {"tid": task_id, "at": now},
                    )
                    conn.execute(
                        sa_text(
                            "INSERT INTO execution_artifact "
                            "(id, task_id, artifact_type, path, size_bytes, created_at) "
                            "VALUES (:aid, :tid, 'SCREENSHOT', :path, 1, :at)"
                        ),
                        [
                            {
                                "aid": str(uuid.uuid4()),
                                "tid": task_id,
                                "path": str(expired_file),
                                "at": now - timedelta(days=31),
                            },
                            {
                                "aid": str(uuid.uuid4()),
                                "tid": task_id,
                                "path": str(fresh_file),
                                "at": now - timedelta(days=1),
                            },
                            {
                                "aid": str(uuid.uuid4()),
                                "tid": task_id,
                                "path": "../outside.txt",
                                "at": now - timedelta(days=31),
                            },
                        ],
                    )

                with Session(engine) as session:
                    service = ResourceCleanupService(artifacts_root=artifacts_root)
                    deleted = service.cleanup_expired_artifacts(
                        session, now, retention_days=30
                    )
                    session.commit()

                assert deleted == 2
                assert not expired_file.exists()
                assert fresh_file.exists()
                assert outside_file.exists()
                with engine.connect() as conn:
                    remaining = conn.execute(
                        sa_text("SELECT COUNT(*) FROM execution_artifact")
                    ).scalar_one()
                assert remaining == 1
            finally:
                engine.dispose()

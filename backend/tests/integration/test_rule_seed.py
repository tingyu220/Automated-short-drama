"""defaults JSON 初始化导入集成测试：临时 SQLite + Alembic + Worker 自动 seed."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"


def _count_rows(session: Session, table_name: str) -> int:
    """统计临时 SQLite 表中行数。"""
    return session.execute(sa_text(f"SELECT count(*) FROM {table_name}")).scalar()


class TestSeedDefaultsIntegration:
    """seed_rules_from_defaults 在真实 SQLite 上的集成测试。"""

    def test_seed_creates_expected_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                result = seed_rules_from_defaults(session, DEFAULTS_PATH)
                session.commit()

                assert result.created_rules == 10
                assert result.skipped_rules == 0
                assert _count_rows(session, "rule_set") == 3
                assert _count_rows(session, "rule_version") == 3
                assert _count_rows(session, "rule_parameter") == 7
                assert _count_rows(session, "template_price_rule") == 2
                assert _count_rows(session, "material_rule_range") == 5
            finally:
                session.close()
                engine.dispose()

    def test_seed_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                seed_rules_from_defaults(session, DEFAULTS_PATH)
                session.commit()
                second = seed_rules_from_defaults(session, DEFAULTS_PATH)
                session.commit()

                assert second.created_rules == 0
                assert second.skipped_rules == 10
                assert _count_rows(session, "rule_set") == 3
                assert _count_rows(session, "rule_version") == 3
                assert _count_rows(session, "rule_parameter") == 7
                assert _count_rows(session, "template_price_rule") == 2
                assert _count_rows(session, "material_rule_range") == 5
            finally:
                session.close()
                engine.dispose()


class TestAutomationWorkerAutoSeed:
    """automation_worker --once 在全新 DB 上自动 seed 默认规则。"""

    def test_worker_once_seeds_defaults_on_fresh_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db_url = f"sqlite:///{db_path}"
            env = {**os.environ, "WORKBUDDY_DATABASE_URL": db_url}

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.bootstrap.automation_worker",
                    "--once",
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
                cwd=PROJECT_ROOT / "backend",
            )
            assert result.returncode == 0, (
                f"worker --once 应退出 0，实际 {result.returncode}\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                assert _count_rows(session, "rule_set") == 3
                assert _count_rows(session, "template_price_rule") == 2
                assert _count_rows(session, "material_rule_range") == 5
            finally:
                session.close()
                engine.dispose()

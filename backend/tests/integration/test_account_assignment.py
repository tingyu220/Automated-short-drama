"""账户同日 CID 占用持久化集成测试。"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.domain.errors.domain_error import ConflictError
from backend.domain.rules.account_sheet import AccountUsage
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.repositories.account_usage_repository import (
    SqlAlchemyAccountUsageRepository,
)


def test_confirmed_usage_persists_and_blocks_same_day_cid_reuse() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_url = f"sqlite:///{Path(tmpdir) / 'account-usage.db'}"
        run_migrations(db_url)
        engine = create_app_engine(db_url)
        with Session(engine) as session:
            repo = SqlAlchemyAccountUsageRepository(session)
            usage = AccountUsage(
                task_id="task-1",
                drama_name="剧一",
                usage_day=date(2026, 8, 10),
                cid="cid-1",
                role="B1",
                sheet_kind="IAA",
                row_number=2,
            )

            repo.record_confirmed([usage])
            session.commit()

            assert repo.used_cids(date(2026, 8, 10)) == {"cid-1"}
            assert repo.used_cids(date(2026, 8, 11)) == set()
            with pytest.raises(ConflictError):
                repo.record_confirmed(
                    [
                        AccountUsage(
                            task_id="task-2",
                            drama_name="剧二",
                            usage_day=date(2026, 8, 10),
                            cid="cid-1",
                            role="B4",
                            sheet_kind="IAA",
                            row_number=3,
                        )
                    ]
                )
        engine.dispose()

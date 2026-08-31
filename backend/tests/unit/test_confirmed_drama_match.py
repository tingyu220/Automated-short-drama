"""人工确认番茄候选的领域值对象与仓储转换。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend.domain.common.timezones import SHANGHAI_TZ
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)


def test_confirmed_drama_match_round_trips_through_task_repository() -> None:
    """确认定位、番茄分钟和确认时间必须作为任务审计数据完整保存。"""
    confirmation = ConfirmedDramaMatch(
        locator_key="/detail/a",
        available_minute=datetime(2026, 8, 19, 0, 53, tzinfo=SHANGHAI_TZ),
        confirmed_at=datetime(2026, 8, 19, 0, 56, tzinfo=timezone.utc),
    )
    task = DramaTask(
        id="task-confirmed-match",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 18, 16, 55, tzinfo=timezone.utc),
        confirmed_drama_match=confirmation,
    )
    with tempfile.TemporaryDirectory() as tmp:
        database_url = f"sqlite:///{Path(tmp) / 'task.db'}"
        config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", database_url)
        config.set_main_option(
            "script_location", str(Path(__file__).parents[2] / "alembic")
        )
        command.upgrade(config, "head")
        engine = create_app_engine(database_url)
        try:
            with Session(engine) as session:
                repo = SqlAlchemyTaskRepository(session)
                repo.add(task)
                session.commit()
                restored = repo.get(task.id)
                assert restored is not None
                assert restored.confirmed_drama_match == confirmation
        finally:
            engine.dispose()

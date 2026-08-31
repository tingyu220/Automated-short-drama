"""链接准备阶段持久化测试。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.repositories.workflow_repository import (
    SqlAlchemyWorkflowRepository,
)


def _task() -> DramaTask:
    return DramaTask(
        id="task-link-ready",
        drama_name="测试漫剧",
        platform="TOMATO",
        available_time=datetime(2026, 8, 16, 8, tzinfo=timezone.utc),
        current_stage="DELIVERY_DRAMA",
        target_stage="LINK_READY",
        delivery_drama_id="dd-1",
        promotion_configs={"IAA": "iaa-番茄-测试漫剧"},
    )


def _upgrade(database_url: str) -> None:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option(
        "script_location", str(Path(__file__).parents[2] / "alembic")
    )
    command.upgrade(config, "head")


def test_task_repository_round_trips_link_readiness_outputs() -> None:
    """防止恢复任务时丢失终点和投放系统产物。"""
    with tempfile.TemporaryDirectory() as tmp:
        database_url = f"sqlite:///{Path(tmp) / 'task.db'}"
        _upgrade(database_url)
        engine = create_app_engine(database_url)
        try:
            with Session(engine) as session:
                repo = SqlAlchemyTaskRepository(session)
                repo.add(_task())
                session.commit()
                loaded = repo.get("task-link-ready")
                assert loaded is not None
                assert loaded.current_stage == "DELIVERY_DRAMA"
                assert loaded.target_stage == "LINK_READY"
                assert loaded.delivery_drama_id == "dd-1"
                assert loaded.promotion_configs == {
                    "IAA": "iaa-番茄-测试漫剧"
                }
        finally:
            engine.dispose()


def test_workflow_repository_records_completed_step_result() -> None:
    """防止阶段完成后无法从数据库恢复其输出。"""
    with tempfile.TemporaryDirectory() as tmp:
        database_url = f"sqlite:///{Path(tmp) / 'workflow.db'}"
        _upgrade(database_url)
        engine = create_app_engine(database_url)
        try:
            with Session(engine) as session:
                SqlAlchemyTaskRepository(session).add(_task())
                repo = SqlAlchemyWorkflowRepository(session)
                step = repo.start_step("task-link-ready", "DELIVERY_DRAMA")
                repo.finish_step(step, {"delivery_drama_id": "dd-1"})
                session.commit()

                steps = repo.list_steps_by_task("task-link-ready")
                assert len(steps) == 1
                assert steps[0].status == "COMPLETED"
                assert steps[0].result_json == {"delivery_drama_id": "dd-1"}
        finally:
            engine.dispose()


def test_workflow_repository_records_failed_step_error() -> None:
    """防止人工处理时丢失阶段错误码和原因。"""
    with tempfile.TemporaryDirectory() as tmp:
        database_url = f"sqlite:///{Path(tmp) / 'failure.db'}"
        _upgrade(database_url)
        engine = create_app_engine(database_url)
        try:
            with Session(engine) as session:
                SqlAlchemyTaskRepository(session).add(_task())
                repo = SqlAlchemyWorkflowRepository(session)
                step = repo.start_step("task-link-ready", "PROMOTION_CONFIG")
                repo.fail_step(step, "RESULT_UNCERTAIN", "保存结果不明确")
                session.commit()

                failed = repo.list_steps_by_task("task-link-ready")[0]
                assert failed.status == "FAILED"
                assert failed.error_code == "RESULT_UNCERTAIN"
                assert failed.error_message == "保存结果不明确"
        finally:
            engine.dispose()

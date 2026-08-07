"""异常 API 集成测试 —— ERROR 事件与 MANUAL_REVIEW 任务合并。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.domain.execution.execution_event import EventLevel
from backend.domain.tasks.drama_task import TaskStatus
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.models.execution import ExecutionEventRecord
from backend.infrastructure.database.models.execution import ExecutionArtifactRecord
from backend.infrastructure.database.models.task import DramaTaskRecord
from backend.interfaces.api.main import create_app


@pytest.fixture
def session_factory(monkeypatch, tmp_path):
    """创建临时数据库，并将全局会话指向它。"""
    db_url = f"sqlite:///{tmp_path / 'exceptions_api.db'}"
    engine = create_app_engine(db_url)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(Path("alembic").resolve()))
    command.upgrade(alembic_cfg, "head")

    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(
        "backend.infrastructure.database.session.SessionLocal", session_factory
    )
    yield session_factory
    engine.dispose()


@pytest.fixture
def client(session_factory):
    """创建测试客户端。"""
    app = create_app(dist_dir=None)
    with TestClient(app) as test_client:
        yield test_client


class TestExceptionsApi:
    """异常列表合并与排序测试。"""

    def test_merge_error_events_and_manual_review_tasks(self, client, session_factory):
        """ERROR 事件与 MANUAL_REVIEW 任务合并，按时间降序。"""
        review_task_id = str(uuid.uuid4())
        normal_task_id = str(uuid.uuid4())
        error_event_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add_all(
                [
                    DramaTaskRecord(
                        id=review_task_id,
                        drama_name="复核剧",
                        platform="TOMATO",
                        available_time=datetime(2026, 8, 6, 12, 0, 0),
                        status=TaskStatus.MANUAL_REVIEW,
                        updated_at=datetime(2026, 8, 6, 10, 30, 0),
                    ),
                    DramaTaskRecord(
                        id=normal_task_id,
                        drama_name="正常剧",
                        platform="TOMATO",
                        available_time=datetime(2026, 8, 6, 12, 0, 0),
                        status=TaskStatus.RUNNING,
                        updated_at=datetime(2026, 8, 6, 9, 0, 0),
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    ExecutionEventRecord(
                        id=error_event_id,
                        task_id=normal_task_id,
                        event_type="STEP_FAILED",
                        level=EventLevel.ERROR,
                        message="提交失败",
                        occurred_at=datetime(2026, 8, 6, 11, 0, 0),
                    ),
                    ExecutionEventRecord(
                        id=str(uuid.uuid4()),
                        task_id=normal_task_id,
                        event_type="TASK_STARTED",
                        level=EventLevel.INFO,
                        message="任务开始",
                        occurred_at=datetime(2026, 8, 6, 8, 0, 0),
                    ),
                ]
            )
            session.commit()

        response = client.get("/api/exceptions")
        assert response.status_code == 200
        data = response.json()
        assert [item["occurred_at"] for item in data] == [
            "2026-08-06T11:00:00",
            "2026-08-06T10:30:00",
        ]
        assert data[0]["id"] == error_event_id
        assert data[0]["task_id"] == normal_task_id
        assert data[0]["level"] == EventLevel.ERROR
        assert data[0]["message"] == "提交失败"
        assert data[0]["step"] == "步骤执行"

        assert data[1]["id"] == review_task_id
        assert data[1]["task_id"] == review_task_id
        assert data[1]["level"] == TaskStatus.MANUAL_REVIEW
        assert data[1]["message"] == "任务进入人工复核"
        assert data[1]["step"] == "人工复核"

    def test_exception_includes_screenshot_paths(
        self, client, session_factory
    ):
        """异常详情带任务最近截图路径。"""
        task_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add(
                DramaTaskRecord(
                    id=task_id,
                    drama_name="截图剧",
                    platform="TOMATO",
                    available_time=datetime(2026, 8, 6, 12, 0, 0),
                    status=TaskStatus.RUNNING,
                    updated_at=datetime(2026, 8, 6, 9, 0, 0),
                )
            )
            session.flush()
            session.add_all(
                [
                    ExecutionEventRecord(
                        id=str(uuid.uuid4()),
                        task_id=task_id,
                        event_type="STEP_FAILED",
                        level=EventLevel.ERROR,
                        message="页面变化",
                        occurred_at=datetime(2026, 8, 6, 10, 0, 0),
                    ),
                    ExecutionArtifactRecord(
                        id=str(uuid.uuid4()),
                        task_id=task_id,
                        artifact_type="SCREENSHOT",
                        path="data/logs/page.png",
                        size_bytes=10,
                        created_at=datetime(2026, 8, 6, 10, 1, 0),
                    ),
                ]
            )
            session.commit()

        data = client.get("/api/exceptions").json()
        assert data[0]["screenshots"] == ["data/logs/page.png"]

    def test_empty_exceptions(self, client):
        """无 ERROR 事件且无复核任务时返回空列表。"""
        response = client.get("/api/exceptions")
        assert response.status_code == 200
        assert response.json() == []

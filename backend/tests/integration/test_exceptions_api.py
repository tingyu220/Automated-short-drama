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
from backend.infrastructure.database.models.task import StepRunRecord, WorkflowRunRecord
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

    def test_manual_review_uses_failed_step_without_duplicate_event(
        self, client, session_factory
    ):
        """人工复核优先展示阶段失败的原始原因，不能重复显示通用事件。"""
        task_id = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())
        step_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add(
                DramaTaskRecord(
                    id=task_id,
                    drama_name="链接剧",
                    platform="TOMATO",
                    available_time=datetime(2026, 8, 6, 12, 0, 0),
                    status=TaskStatus.MANUAL_REVIEW,
                    updated_at=datetime(2026, 8, 6, 10, 0, 0),
                )
            )
            session.flush()
            session.add(
                WorkflowRunRecord(
                    id=workflow_id,
                    task_id=task_id,
                    status="RUNNING",
                    started_at=datetime(2026, 8, 6, 10, 0, 0),
                )
            )
            session.flush()
            session.add(
                StepRunRecord(
                    id=step_id,
                    workflow_run_id=workflow_id,
                    step_name="DELIVERY_DRAMA",
                    status="FAILED",
                    started_at=datetime(2026, 8, 6, 10, 1, 0),
                    finished_at=datetime(2026, 8, 6, 10, 2, 0),
                    error_code="ValueError",
                    error_message="任务没有可用于创建投放剧目的链接",
                )
            )
            session.flush()
            session.add(
                ExecutionEventRecord(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    event_type="MANUAL_REVIEW",
                    level=EventLevel.ERROR,
                    message="链接准备失败，已转人工处理",
                    occurred_at=datetime(2026, 8, 6, 10, 3, 0),
                )
            )
            session.commit()

        data = client.get("/api/exceptions").json()

        assert len(data) == 1
        assert data[0]["id"] == step_id
        assert data[0]["step"] == "搭建投放剧目"
        assert data[0]["error_type"] == "ValueError"
        assert data[0]["message"] == "任务没有可用于创建投放剧目的链接"
        assert data[0]["failure_code"] == "ValueError"
        assert data[0]["failure_details"] is None

    def test_manual_review_uses_error_event_when_no_failed_step(
        self, client, session_factory
    ):
        """旧人工任务没有步骤记录时，也只保留已有的实际错误。"""
        task_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add(
                DramaTaskRecord(
                    id=task_id,
                    drama_name="旧链接剧",
                    platform="TOMATO",
                    available_time=datetime(2026, 8, 6, 12, 0, 0),
                    status=TaskStatus.MANUAL_REVIEW,
                )
            )
            session.flush()
            session.add(
                ExecutionEventRecord(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    event_type="LINK_EXTRACTION",
                    level=EventLevel.ERROR,
                    message="链接提取未完成: NO_LINKS",
                    occurred_at=datetime(2026, 8, 6, 10, 3, 0),
                )
            )
            session.commit()

        data = client.get("/api/exceptions").json()

        assert len(data) == 1
        assert data[0]["message"] == "链接提取未完成: NO_LINKS"
        assert data[0]["step"] == "链接提取"

    def test_manual_review_exposes_event_context_as_failure_evidence(
        self, client, session_factory
    ):
        """没有步骤记录时，也必须从事件上下文还原失败阶段和证据。"""
        task_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add(
                DramaTaskRecord(
                    id=task_id,
                    drama_name="上下文剧",
                    platform="TOMATO",
                    available_time=datetime(2026, 8, 6, 12, 0, 0),
                    status=TaskStatus.MANUAL_REVIEW,
                    current_stage="DELIVERY_DRAMA",
                )
            )
            session.flush()
            session.add(
                ExecutionEventRecord(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    event_type="MANUAL_REVIEW",
                    level=EventLevel.ERROR,
                    message="链接准备失败，已转人工处理",
                    context_json='{"step_name":"DELIVERY_DRAMA","failure_code":"NO_LINKS","details":{"link_status":"NOT_AVAILABLE"}}',
                    occurred_at=datetime(2026, 8, 6, 10, 3, 0),
                )
            )
            session.commit()

        data = client.get("/api/exceptions").json()

        assert data[0]["step"] == "搭建投放剧目"
        assert data[0]["failure_code"] == "NO_LINKS"
        assert data[0]["failure_details"] == {"link_status": "NOT_AVAILABLE"}

    def test_resolved_task_errors_are_not_active_exceptions(
        self, client, session_factory
    ):
        """任务已完成后，历史错误应留在系统记录，不再显示为待处理异常。"""
        task_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add(
                DramaTaskRecord(
                    id=task_id,
                    drama_name="已解决剧",
                    platform="TOMATO",
                    available_time=datetime(2026, 8, 6, 12, 0, 0),
                    status=TaskStatus.LINK_READY,
                )
            )
            session.flush()
            session.add(
                ExecutionEventRecord(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    event_type="STEP_FAILED",
                    level=EventLevel.ERROR,
                    message="旧错误",
                    occurred_at=datetime(2026, 8, 6, 10, 3, 0),
                )
            )
            session.commit()

        assert client.get("/api/exceptions").json() == []

    def test_empty_exceptions(self, client):
        """无 ERROR 事件且无复核任务时返回空列表。"""
        response = client.get("/api/exceptions")
        assert response.status_code == 200
        assert response.json() == []

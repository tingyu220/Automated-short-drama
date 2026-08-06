"""记录 API 集成测试 —— 台账、执行事件与执行产物查询。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.domain.execution.execution_artifact import ArtifactType
from backend.domain.execution.execution_event import EventLevel
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.models.execution import (
    ExecutionArtifactRecord,
    ExecutionEventRecord,
)
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.interfaces.api.main import create_app


@pytest.fixture
def session_factory(monkeypatch, tmp_path):
    """创建临时数据库，并将全局会话指向它。"""
    db_url = f"sqlite:///{tmp_path / 'records_api.db'}"
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


def _create_task(
    session: Session,
    task_id: str,
    *,
    drama_name: str = "记录剧",
    status: str = TaskStatus.COMPLETED,
) -> None:
    """插入 DramaTask。"""
    task = DramaTask(
        id=task_id,
        drama_name=drama_name,
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, 12, 0, 0),
        status=status,
    )
    SqlAlchemyTaskRepository(session).add(task)


class TestRecordsApi:
    """台账、事件与产物查询 API 测试。"""

    def test_list_ledgers_with_task_filter(self, client, session_factory):
        """台账支持全量与 task_id 过滤。"""
        task_a = str(uuid.uuid4())
        task_b = str(uuid.uuid4())
        with session_factory() as session:
            _create_task(session, task_a, drama_name="台账A")
            _create_task(session, task_b, drama_name="台账B")
            repo = SqlAlchemyLedgerRepository(session)
            repo.add(
                TaskLedger(
                    id=str(uuid.uuid4()),
                    task_id=task_a,
                    drama_name="台账A",
                    platform="TOMATO",
                    final_status="COMPLETED",
                    completed_at=datetime(2026, 8, 6, 10, 0, 0),
                )
            )
            repo.add(
                TaskLedger(
                    id=str(uuid.uuid4()),
                    task_id=task_b,
                    drama_name="台账B",
                    platform="JUBIAN",
                    final_status="FAILED",
                    completed_at=datetime(2026, 8, 6, 11, 0, 0),
                )
            )
            session.commit()

        all_data = client.get("/api/records/ledgers").json()
        assert len(all_data) == 2
        assert all_data[0]["drama_name"] == "台账B"
        assert {
            "id",
            "task_id",
            "drama_name",
            "platform",
            "final_status",
            "completed_at",
        } <= set(all_data[0])

        filtered = client.get("/api/records/ledgers", params={"task_id": task_a})
        assert filtered.status_code == 200
        assert [item["task_id"] for item in filtered.json()] == [task_a]

    def test_list_events_with_task_filter(self, client, session_factory):
        """执行事件支持全量与 task_id 过滤。"""
        task_a = str(uuid.uuid4())
        task_b = str(uuid.uuid4())
        with session_factory() as session:
            _create_task(session, task_a)
            _create_task(session, task_b)
            session.add_all(
                [
                    ExecutionEventRecord(
                        id=str(uuid.uuid4()),
                        task_id=task_a,
                        event_type="TASK_STARTED",
                        level=EventLevel.INFO,
                        message="任务A开始",
                        occurred_at=datetime(2026, 8, 6, 9, 0, 0),
                    ),
                    ExecutionEventRecord(
                        id=str(uuid.uuid4()),
                        task_id=task_b,
                        event_type="STEP_FAILED",
                        level=EventLevel.ERROR,
                        message="任务B失败",
                        occurred_at=datetime(2026, 8, 6, 10, 0, 0),
                    ),
                ]
            )
            session.commit()

        all_data = client.get("/api/records/events").json()
        assert len(all_data) == 2
        assert all_data[0]["message"] == "任务B失败"
        assert {
            "id",
            "task_id",
            "event_type",
            "level",
            "message",
            "occurred_at",
        } <= set(all_data[0])

        filtered = client.get("/api/records/events", params={"task_id": task_a})
        assert filtered.status_code == 200
        assert [item["task_id"] for item in filtered.json()] == [task_a]

    def test_list_artifacts_with_task_filter(self, client, session_factory):
        """执行产物支持全量与 task_id 过滤。"""
        task_a = str(uuid.uuid4())
        task_b = str(uuid.uuid4())
        with session_factory() as session:
            _create_task(session, task_a)
            _create_task(session, task_b)
            session.add_all(
                [
                    ExecutionArtifactRecord(
                        id=str(uuid.uuid4()),
                        task_id=task_a,
                        artifact_type=ArtifactType.LOG,
                        path="/tmp/a.log",
                        size_bytes=10,
                        created_at=datetime(2026, 8, 6, 9, 0, 0),
                    ),
                    ExecutionArtifactRecord(
                        id=str(uuid.uuid4()),
                        task_id=task_b,
                        artifact_type=ArtifactType.SCREENSHOT,
                        path="/tmp/b.png",
                        size_bytes=20,
                        created_at=datetime(2026, 8, 6, 10, 0, 0),
                    ),
                ]
            )
            session.commit()

        all_data = client.get("/api/records/artifacts").json()
        assert len(all_data) == 2
        assert all_data[0]["path"] == "/tmp/b.png"
        assert {
            "id",
            "task_id",
            "artifact_type",
            "path",
            "size_bytes",
            "created_at",
        } <= set(all_data[0])

        filtered = client.get("/api/records/artifacts", params={"task_id": task_a})
        assert filtered.status_code == 200
        assert [item["task_id"] for item in filtered.json()] == [task_a]

    def test_unknown_task_returns_empty_lists(self, client):
        """不存在任务的过滤结果均为空列表。"""
        task_id = str(uuid.uuid4())
        assert client.get(
            "/api/records/ledgers", params={"task_id": task_id}
        ).json() == []
        assert client.get(
            "/api/records/events", params={"task_id": task_id}
        ).json() == []
        assert client.get(
            "/api/records/artifacts", params={"task_id": task_id}
        ).json() == []

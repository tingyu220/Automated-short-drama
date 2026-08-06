"""队列 API 集成测试 —— 临时 SQLite + Alembic + TestClient."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.interfaces.api.main import create_app


@pytest.fixture
def session_factory(monkeypatch, tmp_path):
    """创建临时数据库，并将全局会话指向它。"""
    db_url = f"sqlite:///{tmp_path / 'queue_api.db'}"
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


def _create_task(session: Session, task_id: str) -> None:
    """插入 DramaTask。"""
    task = DramaTask(
        id=task_id,
        drama_name="队列剧",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, 12, 0, 0),
        status=TaskStatus.READY,
    )
    SqlAlchemyTaskRepository(session).add(task)


def _create_queue_item(
    session: Session,
    *,
    item_id: str,
    task_id: str,
    state: str,
    available_at: datetime,
    claimed_by: str | None = None,
    attempt_count: int = 0,
) -> None:
    """插入指定状态的 QueueItem。"""
    item = QueueItem(
        id=item_id,
        task_id=task_id,
        state=state,
        available_at=available_at,
        claimed_by=claimed_by,
        lease_until=available_at + timedelta(hours=1) if claimed_by else None,
        attempt_count=attempt_count,
    )
    SqlAlchemyQueueRepository(session).add(item)


class TestQueueApi:
    """队列列表与控制操作 API 测试。"""

    def test_list_filters_by_state(self, client, session_factory):
        """GET /api/queue 支持 state 过滤。"""
        task_id = str(uuid.uuid4())
        queued_id = str(uuid.uuid4())
        paused_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(session, task_id)
            _create_queue_item(
                session,
                item_id=queued_id,
                task_id=task_id,
                state=QueueState.QUEUED,
                available_at=available_at,
            )
            _create_queue_item(
                session,
                item_id=paused_id,
                task_id=task_id,
                state=QueueState.PAUSED,
                available_at=available_at,
            )
            session.commit()

        all_data = client.get("/api/queue").json()
        assert {item["id"] for item in all_data} == {queued_id, paused_id}

        queued_data = client.get(
            "/api/queue", params={"state": QueueState.QUEUED}
        ).json()
        assert [item["id"] for item in queued_data] == [queued_id]
        assert queued_data[0]["task_id"] == task_id

    def test_pause_resume_flow(self, client, session_factory):
        """暂停后恢复，状态迁移正确。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(session, task_id)
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.QUEUED,
                available_at=available_at,
            )
            session.commit()

        paused = client.post(
            f"/api/queue/{item_id}/pause", params={"worker_id": "dashboard"}
        )
        assert paused.status_code == 200
        assert paused.json()["state"] == QueueState.PAUSED
        assert paused.json()["claimed_by"] is None

        resumed = client.post(
            f"/api/queue/{item_id}/resume", params={"worker_id": "dashboard"}
        )
        assert resumed.status_code == 200
        assert resumed.json()["state"] == QueueState.QUEUED

    def test_control_accepts_body_worker_id(self, client, session_factory):
        """worker_id 也可通过请求体传入。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(session, task_id)
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.QUEUED,
                available_at=available_at,
            )
            session.commit()

        response = client.post(
            f"/api/queue/{item_id}/pause",
            json={"worker_id": "dashboard"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == QueueState.PAUSED

    def test_cancel_and_retry(self, client, session_factory):
        """取消与重试状态迁移正确。"""
        task_id = str(uuid.uuid4())
        cancel_id = str(uuid.uuid4())
        retry_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(session, task_id)
            _create_queue_item(
                session,
                item_id=cancel_id,
                task_id=task_id,
                state=QueueState.QUEUED,
                available_at=available_at,
            )
            _create_queue_item(
                session,
                item_id=retry_id,
                task_id=task_id,
                state=QueueState.FAILED,
                available_at=available_at,
                claimed_by="worker-1",
                attempt_count=3,
            )
            session.commit()

        cancelled = client.post(
            f"/api/queue/{cancel_id}/cancel", params={"worker_id": "dashboard"}
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == QueueState.CANCELLED

        retried = client.post(
            f"/api/queue/{retry_id}/retry", params={"worker_id": "dashboard"}
        )
        assert retried.status_code == 200
        assert retried.json()["state"] == QueueState.QUEUED
        assert retried.json()["attempt_count"] == 0
        assert retried.json()["claimed_by"] is None

    def test_worker_mismatch_returns_409(self, client, session_factory):
        """CLAIMED 项由其他 worker 操作返回 409。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(session, task_id)
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.CLAIMED,
                available_at=available_at,
                claimed_by="worker-A",
            )
            session.commit()

        response = client.post(
            f"/api/queue/{item_id}/pause", params={"worker_id": "worker-B"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "CONFLICT"

    def test_worker_id_required(self, client, session_factory):
        """缺少 worker_id 返回 422。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(session, task_id)
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.QUEUED,
                available_at=available_at,
            )
            session.commit()

        response = client.post(f"/api/queue/{item_id}/pause")
        assert response.status_code == 422

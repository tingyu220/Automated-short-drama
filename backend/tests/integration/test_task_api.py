"""任务 API 集成测试 —— 临时 SQLite + Alembic + TestClient."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.execution.execution_event import ExecutionEvent
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.execution_repository import (
    SqlAlchemyExecutionRepository,
)
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
    db_url = f"sqlite:///{tmp_path / 'task_api.db'}"
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
    *,
    task_id: str,
    drama_name: str = "测试剧",
    platform: str = "TOMATO",
    available_time: datetime,
    status: str = TaskStatus.WAITING_TIME,
    owner: str | None = None,
) -> None:
    """插入 DramaTask。"""
    task = DramaTask(
        id=task_id,
        drama_name=drama_name,
        platform=platform,
        available_time=available_time,
        status=status,
        owner=owner,
    )
    SqlAlchemyTaskRepository(session).add(task)


def _create_queue_item(
    session: Session,
    *,
    item_id: str,
    task_id: str,
    state: str = QueueState.WAITING_TIME,
    available_at: datetime,
    claimed_by: str | None = None,
    attempt_count: int = 0,
    failure_code: str | None = None,
) -> None:
    """插入 QueueItem。"""
    item = QueueItem(
        id=item_id,
        task_id=task_id,
        state=state,
        available_at=available_at,
        claimed_by=claimed_by,
        lease_until=available_at + timedelta(hours=1) if claimed_by else None,
        attempt_count=attempt_count,
        failure_code=failure_code,
    )
    SqlAlchemyQueueRepository(session).add(item)


class TestTaskApi:
    """GET /api/tasks 列表与筛选测试。"""

    def test_list_sorted_by_available_time_desc_with_queue_state(
        self, client, session_factory
    ):
        """列表按 available_time 降序，并携带最新队列状态。"""
        with session_factory() as session:
            early_id = str(uuid.uuid4())
            late_id = str(uuid.uuid4())
            _create_task(
                session,
                task_id=early_id,
                drama_name="早播剧",
                available_time=datetime(2026, 8, 6, 9, 0, 0),
            )
            _create_task(
                session,
                task_id=late_id,
                drama_name="晚播剧",
                available_time=datetime(2026, 8, 6, 21, 0, 0),
            )
            _create_queue_item(
                session,
                item_id=str(uuid.uuid4()),
                task_id=late_id,
                state=QueueState.QUEUED,
                available_at=datetime(2026, 8, 6, 21, 0, 0),
            )
            session.commit()

        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert [item["id"] for item in data] == [late_id, early_id]
        assert data[0]["queue_state"] == QueueState.QUEUED
        assert data[1]["queue_state"] is None
        assert data[0]["current_stage"] == "WAITING_AVAILABLE_TIME"
        assert data[0]["target_stage"] == "LINK_READY"

    def test_manual_scan_runs_scheduler_and_returns_statistics(
        self, client, session_factory, monkeypatch
    ):
        """手动扫描必须执行一次调度并返回新增/入队统计。"""
        source = DramaTask(
            id="source-1",
            source_key="source-key-1",
            drama_name="手动扫描剧",
            platform="TOMATO",
            available_time=datetime.now(timezone.utc),
            status=TaskStatus.WAITING_TIME,
        )

        class FakeFeishu:
            def fetch_tasks(self, day):
                return [source]

        monkeypatch.setattr(
            "backend.interfaces.api.routes.tasks.build_scheduler_feishu",
            lambda settings: (FakeFeishu(), "test"),
        )

        response = client.post("/api/tasks/scan")

        assert response.status_code == 200
        payload = response.json()
        assert payload["created_tasks"] == 1
        assert payload["enqueued"] == 1
        with session_factory() as session:
            assert SqlAlchemyTaskRepository(session).get_by_source_key("source-key-1")

    def test_list_filters(self, client, session_factory):
        """date/platform/status/q 均可过滤。"""
        with session_factory() as session:
            ids = [str(uuid.uuid4()) for _ in range(3)]
            _create_task(
                session,
                task_id=ids[0],
                drama_name="番茄爆款",
                platform="TOMATO",
                status=TaskStatus.READY,
                available_time=datetime(2026, 8, 6, 10, 0, 0),
            )
            _create_task(
                session,
                task_id=ids[1],
                drama_name="剧变热播",
                platform="JUBIAN",
                status=TaskStatus.WAITING_TIME,
                available_time=datetime(2026, 8, 7, 10, 0, 0),
            )
            _create_task(
                session,
                task_id=ids[2],
                drama_name="番茄老剧",
                platform="TOMATO",
                status=TaskStatus.COMPLETED,
                available_time=datetime(2026, 8, 6, 11, 0, 0),
            )
            session.commit()

        date_data = client.get("/api/tasks", params={"date": "2026-08-06"}).json()
        assert {item["id"] for item in date_data} == {ids[0], ids[2]}

        platform_data = client.get("/api/tasks", params={"platform": "JUBIAN"}).json()
        assert [item["id"] for item in platform_data] == [ids[1]]

        status_data = client.get(
            "/api/tasks", params={"status": TaskStatus.COMPLETED}
        ).json()
        assert [item["id"] for item in status_data] == [ids[2]]

        query_data = client.get("/api/tasks", params={"q": "爆款"}).json()
        assert [item["id"] for item in query_data] == [ids[0]]

    def test_detail_returns_queue_and_ledger_fields(self, client, session_factory):
        """详情包含队列项与台账字段。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        ledger_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                drama_name="详情剧",
                available_time=available_at,
                owner="小明",
            )
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.CLAIMED,
                available_at=available_at,
                claimed_by="worker-1",
                attempt_count=2,
            )
            SqlAlchemyLedgerRepository(session).add(
                TaskLedger(
                    id=ledger_id,
                    task_id=task_id,
                    drama_name="详情剧",
                    platform="TOMATO",
                    final_status="COMPLETED",
                )
            )
            session.commit()

        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["queue_item_id"] == item_id
        assert data["queue_state"] == QueueState.CLAIMED
        assert data["attempt_count"] == 2
        assert data["claimed_by"] == "worker-1"
        assert data["lease_until"] is not None
        assert data["ledger_id"] == ledger_id

    def test_detail_missing_returns_404(self, client):
        """不存在任务返回 404。"""
        response = client.get(f"/api/tasks/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_enqueue_creates_then_duplicate_conflict(self, client, session_factory):
        """首次入队创建 WAITING_TIME 项，重复入队返回 409。"""
        task_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                available_time=available_at,
            )
            session.commit()

        response = client.post(f"/api/tasks/{task_id}/enqueue")
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"] == task_id
        assert data["state"] == QueueState.WAITING_TIME
        assert datetime.fromisoformat(data["available_at"]) == available_at

        duplicate = client.post(f"/api/tasks/{task_id}/enqueue")
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "CONFLICT"

    def test_enqueue_persists_requested_link_extraction_target(
        self, client, session_factory
    ):
        """手动选择仅提链后，Worker 必须能读到该运行终点。"""
        task_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                available_time=available_at,
            )
            session.commit()

        response = client.post(
            f"/api/tasks/{task_id}/enqueue",
            json={"target_stage": "LINK_EXTRACTION"},
        )

        assert response.status_code == 201
        detail = client.get(f"/api/tasks/{task_id}").json()
        assert detail["target_stage"] == "LINK_EXTRACTION"
        assert detail["current_stage"] == "WAITING_AVAILABLE_TIME"
        assert detail["link_set"] == {}
        assert detail["promotion_configs"] == {}

    def test_enqueue_rejects_plan_stage_target(self, client, session_factory):
        """本期接口不得绕过边界进入计划阶段。"""
        task_id = str(uuid.uuid4())
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                available_time=datetime(2026, 8, 16, 12, tzinfo=timezone.utc),
            )
            session.commit()

        response = client.post(
            f"/api/tasks/{task_id}/enqueue",
            json={"target_stage": "SUBMIT_PLAN"},
        )

        assert response.status_code == 422

    def test_enqueue_reuses_terminal_item(self, client, session_factory):
        """终态队列项可复用为新的 WAITING_TIME 项。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                available_time=available_at,
            )
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.CANCELLED,
                available_at=available_at,
                claimed_by="worker-1",
                attempt_count=3,
            )
            session.commit()

        response = client.post(f"/api/tasks/{task_id}/enqueue")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == item_id
        assert data["state"] == QueueState.WAITING_TIME
        assert data["attempt_count"] == 0
        assert data["claimed_by"] is None

    def test_enqueue_reuses_dry_run_item(self, client, session_factory):
        """演练完成项视为终态，继续操作应复用并重新入队。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                available_time=available_at,
                status=TaskStatus.DRY_RUN,
            )
            task = SqlAlchemyTaskRepository(session).get(task_id)
            assert task is not None
            task.link_set = {"IAA": "mock://iaa/test"}
            task.link_status = "VALIDATED"
            task.delivery_drama_id = "mock-drama"
            task.promotion_configs = {"IAA": "mock-config"}
            task.current_stage = "LINK_READY"
            SqlAlchemyTaskRepository(session).update(task)
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.DRY_RUN,
                available_at=available_at,
            )
            session.commit()

        response = client.post(f"/api/tasks/{task_id}/enqueue")

        assert response.status_code == 200
        assert response.json()["id"] == item_id
        assert response.json()["state"] == QueueState.WAITING_TIME
        detail = client.get(f"/api/tasks/{task_id}").json()
        assert detail["status"] == TaskStatus.WAITING_TIME
        assert detail["current_stage"] == "WAITING_AVAILABLE_TIME"
        assert detail["link_set"] == {}
        assert detail["delivery_drama_id"] == ""
        assert detail["promotion_configs"] == {}

    def test_enqueue_retries_manual_review_item_to_selected_target(
        self, client, session_factory
    ):
        """人工处理任务可从详情直接重新安排到链接就绪。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                available_time=available_at,
                status=TaskStatus.MANUAL_REVIEW,
            )
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.MANUAL_REVIEW,
                available_at=available_at,
                attempt_count=3,
                failure_code="ValueError",
            )
            session.commit()

        response = client.post(
            f"/api/tasks/{task_id}/enqueue",
            json={"target_stage": "LINK_READY"},
        )

        assert response.status_code == 200
        assert response.json()["id"] == item_id
        assert response.json()["state"] == QueueState.QUEUED
        assert response.json()["failure_code"] is None
        assert client.get(f"/api/tasks/{task_id}").json()["target_stage"] == "LINK_READY"

    def test_confirm_drama_match_saves_candidate_and_requeues(
        self, client, session_factory
    ):
        """人工确认候选后继续执行不再依赖原始严格时间匹配。"""
        task_id = str(uuid.uuid4())
        item_id = str(uuid.uuid4())
        available_at = datetime(2026, 8, 19, 0, 55, tzinfo=timezone.utc)
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                drama_name="剧A",
                available_time=available_at,
                status=TaskStatus.MANUAL_REVIEW,
            )
            task = SqlAlchemyTaskRepository(session).get(task_id)
            assert task is not None
            task.link_status = "DRAMA_MISMATCH"
            SqlAlchemyTaskRepository(session).update(task)
            _create_queue_item(
                session,
                item_id=item_id,
                task_id=task_id,
                state=QueueState.MANUAL_REVIEW,
                available_at=available_at,
                failure_code="DRAMA_MISMATCH",
            )
            SqlAlchemyExecutionRepository(session).add_event(
                ExecutionEvent(
                    task_id=task_id,
                    event_type="MANUAL_REVIEW",
                    level="ERROR",
                    message="链接提取未完成: DRAMA_MISMATCH",
                    context_json={
                        "candidates": [
                            {
                                "drama_name": "剧A",
                                "minute": "2026-08-19T00:53:00+08:00",
                                "locator_key": "/detail/a",
                            }
                        ]
                    },
                )
            )
            session.commit()

        response = client.post(
            f"/api/tasks/{task_id}/confirm-drama-match",
            json={"locator_key": "/detail/a"},
        )

        assert response.status_code == 200
        assert response.json()["state"] == QueueState.QUEUED
        detail = client.get(f"/api/tasks/{task_id}").json()
        assert detail["confirmed_drama_match"]["locator_key"] == "/detail/a"

    def test_enqueue_rejects_unconfirmed_drama_mismatch(
        self, client, session_factory
    ):
        """普通继续不能绕过剧目候选人工确认。"""
        task_id = str(uuid.uuid4())
        with session_factory() as session:
            _create_task(
                session,
                task_id=task_id,
                drama_name="剧A",
                available_time=datetime(2026, 8, 19, 0, 55, tzinfo=timezone.utc),
                status=TaskStatus.MANUAL_REVIEW,
            )
            task = SqlAlchemyTaskRepository(session).get(task_id)
            assert task is not None
            task.link_status = "DRAMA_MISMATCH"
            SqlAlchemyTaskRepository(session).update(task)
            session.commit()

        response = client.post(f"/api/tasks/{task_id}/enqueue")

        assert response.status_code == 409
        assert response.json()["code"] == "CONFLICT"

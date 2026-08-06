"""WorkerExecutionService 与 ExecutionRepository.add_event 测试。"""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.application.services.worker_execution import (
    ExecutionOutcome,
    WorkerExecutionService,
    mock_worker_executor,
)
from backend.domain.execution.execution_event import EventLevel, ExecutionEvent
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.task import DramaTaskRecord
from backend.infrastructure.database.repositories.execution_repository import (
    SqlAlchemyExecutionRepository,
)

NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)


class FakeQueueRepository:
    """内存 QueueRepository 假实现。"""

    def __init__(self, items: dict[str, QueueItem] | None = None) -> None:
        self._items = items or {}

    def add(self, item: QueueItem) -> QueueItem:
        self._items[item.id] = item
        return item

    def get(self, item_id: str) -> QueueItem | None:
        return self._items.get(item_id)

    def update(self, item: QueueItem) -> QueueItem:
        self._items[item.id] = item
        return item

    def list_by_state(self, state: str) -> list[QueueItem]:
        return [i for i in self._items.values() if i.state == state]

    def list_all(self) -> list[QueueItem]:
        return list(self._items.values())

    def list_by_task(self, task_id: str) -> list[QueueItem]:
        return [i for i in self._items.values() if i.task_id == task_id]


class FakeTaskRepository:
    """内存 TaskRepository 假实现。"""

    def __init__(self, tasks: dict[str, DramaTask] | None = None) -> None:
        self._tasks = tasks or {}

    def add(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> DramaTask | None:
        return self._tasks.get(task_id)

    def update(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task

    def list_by_state(self, state: str) -> list[DramaTask]:
        return [t for t in self._tasks.values() if t.status == state]

    def list_by_filters(self, **kwargs) -> list[DramaTask]:
        return list(self._tasks.values())


class FakeLedgerRepository:
    """内存 LedgerRepository 假实现。"""

    def __init__(self) -> None:
        self._ledgers: dict[str, object] = {}

    def add(self, ledger):
        self._ledgers[ledger.id] = ledger
        return ledger

    def get(self, ledger_id: str):
        return self._ledgers.get(ledger_id)

    def update(self, ledger):
        self._ledgers[ledger.id] = ledger
        return ledger

    def list_by_task(self, task_id: str):
        return [l for l in self._ledgers.values() if l.task_id == task_id]

    def list_all(self):
        return list(self._ledgers.values())


class FakeExecutionRepository:
    """内存 ExecutionRepository 假实现。"""

    def __init__(self) -> None:
        self._events: list[ExecutionEvent] = []

    def add_event(self, execution_event: ExecutionEvent) -> ExecutionEvent:
        if not execution_event.id:
            execution_event.id = str(uuid.uuid4())
        self._events.append(execution_event)
        return execution_event

    def list_events(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
    ) -> list[ExecutionEvent]:
        result = [
            e
            for e in self._events
            if (task_id is None or e.task_id == task_id)
            and (level is None or e.level == level)
        ]
        return result

    def list_artifacts(self, *, task_id: str | None = None):
        return []


def _make_context(worker_id: str = "worker-1"):
    """构造 CLAIMED 队列项与关联任务，返回各仓储。"""
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=NOW,
        status=TaskStatus.WAITING_TIME,
    )
    item = QueueItem(
        id="queue-1",
        task_id=task.id,
        state=QueueState.CLAIMED,
        claimed_by=worker_id,
        available_at=NOW,
    )
    queue_repo = FakeQueueRepository({"queue-1": item})
    task_repo = FakeTaskRepository({"task-1": task})
    ledger_repo = FakeLedgerRepository()
    event_repo = FakeExecutionRepository()
    return task, item, queue_repo, task_repo, ledger_repo, event_repo


class TestWorkerExecutionService:
    """WorkerExecutionService.process_claimed 单元测试。"""

    def test_success_flow_completes_queue_task_and_ledger(self):
        task, item, queue_repo, task_repo, ledger_repo, event_repo = _make_context()
        service = WorkerExecutionService(
            mock_worker_executor(),
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            "worker-1",
        )

        result = service.process_claimed(item, NOW)

        assert result.queue_item_id == "queue-1"
        assert result.final_queue_state == QueueState.COMPLETED
        assert result.ledger_id
        assert result.event_count == 1
        assert queue_repo.get("queue-1").state == QueueState.COMPLETED
        assert task_repo.get("task-1").status == TaskStatus.COMPLETED
        ledger = ledger_repo.list_by_task(task.id)[0]
        assert ledger.final_status == "COMPLETED"
        assert ledger.album_id == "album-mock"
        assert ledger.product_id == "product-mock"
        assert ledger.external_task_id == "mock-external-1"
        assert ledger.task_name == "mock-task"
        events = event_repo.list_events(task_id=task.id)
        assert [e.event_type for e in events] == ["MOCK_EXECUTED"]

    def test_manual_review_outcome_writes_error_event(self):
        task, item, queue_repo, task_repo, ledger_repo, event_repo = _make_context()

        def executor(_task, _item):
            return ExecutionOutcome(status="MANUAL_REVIEW")

        service = WorkerExecutionService(
            executor,
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            "worker-1",
        )

        result = service.process_claimed(item, NOW)

        assert result.final_queue_state == QueueState.MANUAL_REVIEW
        assert result.ledger_id is None
        assert result.event_count == 1
        assert queue_repo.get("queue-1").state == QueueState.MANUAL_REVIEW
        assert task_repo.get("task-1").status == TaskStatus.MANUAL_REVIEW
        errors = event_repo.list_events(task_id=task.id, level=EventLevel.ERROR)
        assert len(errors) == 1
        assert errors[0].message

    def test_failed_outcome_moves_queue_and_task_to_failed(self):
        task, item, queue_repo, task_repo, ledger_repo, event_repo = _make_context()

        def executor(_task, _item):
            return ExecutionOutcome(status="FAILED")

        service = WorkerExecutionService(
            executor,
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            "worker-1",
        )

        result = service.process_claimed(item, NOW)

        assert result.final_queue_state == QueueState.FAILED
        assert result.ledger_id is None
        assert queue_repo.get("queue-1").state == QueueState.FAILED
        assert task_repo.get("task-1").status == TaskStatus.FAILED
        errors = event_repo.list_events(task_id=task.id, level=EventLevel.ERROR)
        assert len(errors) == 1

    def test_executor_exception_is_treated_as_manual_review(self):
        task, item, queue_repo, task_repo, ledger_repo, event_repo = _make_context()

        def boom(_task, _item):
            raise RuntimeError("boom")

        service = WorkerExecutionService(
            boom,
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            "worker-1",
        )

        result = service.process_claimed(item, NOW)

        assert result.final_queue_state == QueueState.MANUAL_REVIEW
        assert task_repo.get("task-1").status == TaskStatus.MANUAL_REVIEW
        errors = event_repo.list_events(task_id=task.id, level=EventLevel.ERROR)
        assert len(errors) == 1
        assert "boom" in errors[0].message

    def test_non_claimed_item_is_skipped(self):
        task, item, queue_repo, task_repo, ledger_repo, event_repo = _make_context()
        item.state = QueueState.QUEUED
        service = WorkerExecutionService(
            mock_worker_executor(),
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            "worker-1",
        )

        result = service.process_claimed(item, NOW)

        assert result.queue_item_id == "queue-1"
        assert result.final_queue_state == QueueState.QUEUED
        assert result.ledger_id is None
        assert result.event_count == 0
        assert queue_repo.get("queue-1").state == QueueState.QUEUED
        assert task_repo.get("task-1").status == TaskStatus.WAITING_TIME
        assert event_repo.list_events(task_id=task.id) == []


class TestAddEvent:
    """ExecutionRepository.add_event 持久化测试。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(engine)
        self.session = Session(engine)
        yield
        self.session.close()
        engine.dispose()
        self.tmpdir.cleanup()

    def test_add_event_generates_id_and_round_trips(self):
        task_id = str(uuid.uuid4())
        self.session.add(
            DramaTaskRecord(
                id=task_id,
                drama_name="测试剧",
                platform="TOMATO",
                available_time=NOW,
            )
        )
        self.session.flush()
        repo = SqlAlchemyExecutionRepository(self.session)
        execution_event = ExecutionEvent(
            task_id=task_id,
            event_type="MOCK_EXECUTED",
            message="执行完成",
            level=EventLevel.INFO,
            context_json={"step": "submit"},
            occurred_at=NOW,
        )

        saved = repo.add_event(execution_event)
        self.session.commit()

        assert saved.id
        fetched = repo.list_events(task_id=task_id)
        assert len(fetched) == 1
        assert fetched[0].id == saved.id
        assert fetched[0].context_json == {"step": "submit"}

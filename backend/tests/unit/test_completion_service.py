"""completion_service 单元测试 —— 使用 fake repositories."""
from __future__ import annotations

import pytest

from backend.application.services.completion_service import complete_task
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus


class FakeSession:
    """最小 fake session."""

    def add(self, obj: object) -> None:
        pass

    def flush(self) -> None:
        pass

    def get(self, model: type, ident: str) -> object | None:
        return None

    def execute(self, stmt: object):
        raise NotImplementedError("FakeSession 不应执行 SQL")


class FakeQueueRepository:
    """模拟 QueueRepository."""

    def __init__(self, items: dict[str, QueueItem] | None = None) -> None:
        self._items = items or {}

    def get(self, item_id: str) -> QueueItem | None:
        return self._items.get(item_id)

    def update(self, item: QueueItem) -> QueueItem:
        self._items[item.id] = item
        return item


class FakeTaskRepository:
    """模拟 TaskRepository."""

    def __init__(self, tasks: dict[str, DramaTask] | None = None) -> None:
        self._tasks = tasks or {}

    def get(self, task_id: str) -> DramaTask | None:
        return self._tasks.get(task_id)

    def update(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task


class FakeLedgerRepository:
    """模拟 LedgerRepository."""

    def __init__(self) -> None:
        self._ledgers: dict[str, TaskLedger] = {}

    def add(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger


def make_item(
    item_id: str = "qi-1",
    state: str = QueueState.CLAIMED,
    claimed_by: str = "worker-1",
) -> QueueItem:
    return QueueItem(
        id=item_id, task_id="task-1", state=state, claimed_by=claimed_by
    )


def make_task(task_id: str = "task-1") -> DramaTask:
    from datetime import datetime, timezone

    return DramaTask(
        id=task_id,
        drama_name="test-drama",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        status=TaskStatus.RUNNING,
    )


class TestCompleteTask:
    """complete_task 单元测试."""

    # ── fixture helpers ──
    @staticmethod
    def _patch(monkeypatch, queue_repo, task_repo, ledger_repo):
        monkeypatch.setattr(
            "backend.application.services.completion_service.SqlAlchemyQueueRepository",
            lambda session: queue_repo,
        )
        monkeypatch.setattr(
            "backend.application.services.completion_service.SqlAlchemyTaskRepository",
            lambda session: task_repo,
        )
        monkeypatch.setattr(
            "backend.application.services.completion_service.SqlAlchemyLedgerRepository",
            lambda session: ledger_repo,
        )

    # ── 测试用例 ──

    def test_complete_success_returns_ledger(self, monkeypatch):
        """成功完成返回 ledger."""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        self._patch(monkeypatch, queue_repo, task_repo, ledger_repo)

        result = complete_task(FakeSession(), "qi-1", "worker-1")

        assert isinstance(result, TaskLedger)
        assert result.task_id == "task-1"
        assert result.drama_name == "test-drama"
        assert result.platform == "TOMATO"
        assert result.final_status == "COMPLETED"
        assert result.completed_at is not None
        # 验证队列项状态已迁移
        assert item.state == QueueState.COMPLETED
        # 验证 DramaTask 状态已更新
        assert task.status == TaskStatus.COMPLETED

    def test_complete_with_ledger_fields(self, monkeypatch):
        """传入 ledger_fields 正确合并."""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        self._patch(monkeypatch, queue_repo, task_repo, ledger_repo)

        fields = {
            "album_id": "alb-123",
            "product_id": "prod-456",
            "rule_version": "v2",
        }
        result = complete_task(FakeSession(), "qi-1", "worker-1", fields)

        assert result.album_id == "alb-123"
        assert result.product_id == "prod-456"
        assert result.rule_version == "v2"
        # 未传字段使用默认空串
        assert result.task_name == ""
        assert result.config_version == ""

    def test_worker_mismatch_raises_conflict(self, monkeypatch):
        """claimed_by 不匹配抛 ConflictError."""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-A")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        self._patch(monkeypatch, queue_repo, task_repo, ledger_repo)

        with pytest.raises(ConflictError):
            complete_task(FakeSession(), "qi-1", "worker-B")

    def test_invalid_state_raises_conflict(self, monkeypatch):
        """非 CLAIMED/RUNNING 状态抛 ConflictError."""
        for state in [QueueState.QUEUED, QueueState.WAITING_TIME,
                       QueueState.COMPLETED, QueueState.CANCELLED]:
            item = make_item("qi-1", state, "worker-1")
            task = make_task("task-1")
            queue_repo = FakeQueueRepository({"qi-1": item})
            task_repo = FakeTaskRepository({"task-1": task})
            ledger_repo = FakeLedgerRepository()
            self._patch(monkeypatch, queue_repo, task_repo, ledger_repo)

            with pytest.raises(ConflictError):
                complete_task(FakeSession(), "qi-1", "worker-1")

    def test_running_state_allowed(self, monkeypatch):
        """RUNNING 状态允许完成出队."""
        item = make_item("qi-1", QueueState.RUNNING, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        self._patch(monkeypatch, queue_repo, task_repo, ledger_repo)

        result = complete_task(FakeSession(), "qi-1", "worker-1")

        assert result.final_status == "COMPLETED"
        assert item.state == QueueState.COMPLETED

    def test_nonexistent_queue_item_raises_not_found(self, monkeypatch):
        """不存在的队列项抛 NotFoundError."""
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        self._patch(monkeypatch, queue_repo, task_repo, ledger_repo)

        with pytest.raises(NotFoundError):
            complete_task(FakeSession(), "nonexistent", "worker-1")

"""completion_service 单元测试 —— 使用 fake repositories 注入."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.application.services.completion_service import complete_task
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus


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

    def update(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def list_by_task(self, task_id: str) -> list[TaskLedger]:
        return [l for l in self._ledgers.values() if l.task_id == task_id]


def make_item(
    item_id: str = "qi-1",
    state: str = QueueState.CLAIMED,
    claimed_by: str = "worker-1",
) -> QueueItem:
    return QueueItem(
        id=item_id, task_id="task-1", state=state, claimed_by=claimed_by
    )


def make_task(task_id: str = "task-1") -> DramaTask:
    return DramaTask(
        id=task_id,
        drama_name="test-drama",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        status=TaskStatus.RUNNING,
    )


class TestCompleteTask:
    """complete_task 单元测试."""

    def test_complete_success_returns_ledger(self):
        """成功完成返回 ledger."""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()

        result = complete_task("qi-1", "worker-1", queue_repo, task_repo, ledger_repo)

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

    def test_complete_with_ledger_fields(self):
        """传入 ledger_fields 正确合并."""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()

        fields = {
            "album_id": "alb-123",
            "product_id": "prod-456",
            "rule_version": "v2",
        }
        result = complete_task(
            "qi-1", "worker-1", queue_repo, task_repo, ledger_repo, fields
        )

        assert result.album_id == "alb-123"
        assert result.product_id == "prod-456"
        assert result.rule_version == "v2"
        # 未传字段使用默认空串
        assert result.task_name == ""
        assert result.config_version == ""

    def test_complete_twice_reuses_existing_ledger(self):
        """同一 task 二次完成复用台账，不重复创建。"""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()

        first = complete_task(
            "qi-1",
            "worker-1",
            queue_repo,
            task_repo,
            ledger_repo,
            {"external_task_id": "ext-1"},
        )
        item.state = QueueState.CLAIMED
        second = complete_task(
            "qi-1",
            "worker-1",
            queue_repo,
            task_repo,
            ledger_repo,
            {"external_task_id": "ext-2", "product_id": "prod-2"},
        )

        assert second.id == first.id
        assert len(ledger_repo.list_by_task("task-1")) == 1
        assert second.external_task_id == "ext-2"
        assert second.product_id == "prod-2"

    def test_worker_mismatch_raises_conflict(self):
        """claimed_by 不匹配抛 ConflictError."""
        item = make_item("qi-1", QueueState.CLAIMED, "worker-A")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()

        with pytest.raises(ConflictError):
            complete_task("qi-1", "worker-B", queue_repo, task_repo, ledger_repo)

    def test_invalid_state_raises_conflict(self):
        """非 CLAIMED/RUNNING 状态抛 ConflictError."""
        for state in [
            QueueState.QUEUED,
            QueueState.WAITING_TIME,
            QueueState.COMPLETED,
            QueueState.CANCELLED,
        ]:
            item = make_item("qi-1", state, "worker-1")
            task = make_task("task-1")
            queue_repo = FakeQueueRepository({"qi-1": item})
            task_repo = FakeTaskRepository({"task-1": task})
            ledger_repo = FakeLedgerRepository()

            with pytest.raises(ConflictError):
                complete_task("qi-1", "worker-1", queue_repo, task_repo, ledger_repo)

    def test_running_state_allowed(self):
        """RUNNING 状态允许完成出队."""
        item = make_item("qi-1", QueueState.RUNNING, "worker-1")
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()

        result = complete_task("qi-1", "worker-1", queue_repo, task_repo, ledger_repo)

        assert result.final_status == "COMPLETED"
        assert item.state == QueueState.COMPLETED

    def test_nonexistent_queue_item_raises_not_found(self):
        """不存在的队列项抛 NotFoundError."""
        task = make_task("task-1")
        queue_repo = FakeQueueRepository({})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()

        with pytest.raises(NotFoundError):
            complete_task("nonexistent", "worker-1", queue_repo, task_repo, ledger_repo)

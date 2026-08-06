"""task_control_service 单元测试 —— 使用 fake repositories 注入."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.application.services.task_control_service import (
    cancel_task,
    mark_manual_review,
    pause_task,
    resume_task,
    retry_task,
)
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus


class FakeQueueRepository:
    """模拟 QueueRepository."""

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


class FakeTaskRepository:
    """模拟 TaskRepository."""

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


def make_item(
    item_id: str = "qi-1",
    state: str = QueueState.QUEUED,
    claimed_by: str | None = None,
    lease_until: datetime | None = None,
    attempt_count: int = 0,
) -> QueueItem:
    """构造测试用 QueueItem。"""
    return QueueItem(
        id=item_id,
        task_id="task-1",
        state=state,
        claimed_by=claimed_by,
        lease_until=lease_until,
        attempt_count=attempt_count,
    )


class TestPauseTask:
    """pause_task 单元测试。"""

    def test_pause_queued_success(self):
        item = make_item("qi-1", QueueState.QUEUED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = pause_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert result is item
        assert result.state == QueueState.PAUSED
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_pause_claimed_success(self):
        item = make_item(
            "qi-1", QueueState.CLAIMED, "worker-1", datetime(2026, 8, 6, 12, 0)
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = pause_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert result.state == QueueState.PAUSED
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_pause_running_success(self):
        item = make_item(
            "qi-1", QueueState.RUNNING, "worker-1", datetime(2026, 8, 6, 12, 0)
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = pause_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert result.state == QueueState.PAUSED
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_pause_wrong_worker_raises_conflict(self):
        item = make_item("qi-1", QueueState.CLAIMED, "worker-A")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            pause_task(queue_repo, task_repo, "qi-1", "worker-B")

        assert item.state == QueueState.CLAIMED
        assert item.claimed_by == "worker-A"

    def test_pause_invalid_state_raises_conflict(self):
        item = make_item("qi-1", QueueState.COMPLETED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            pause_task(queue_repo, task_repo, "qi-1", "worker-1")

    def test_pause_nonexistent_raises_not_found(self):
        queue_repo = FakeQueueRepository()
        task_repo = FakeTaskRepository()

        with pytest.raises(NotFoundError):
            pause_task(queue_repo, task_repo, "missing", "worker-1")


class TestResumeTask:
    """resume_task 单元测试。"""

    def test_resume_success(self):
        item = make_item("qi-1", QueueState.PAUSED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = resume_task(queue_repo, task_repo, "qi-1")

        assert result is item
        assert result.state == QueueState.QUEUED

    def test_resume_invalid_state_raises_conflict(self):
        item = make_item("qi-1", QueueState.RUNNING)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            resume_task(queue_repo, task_repo, "qi-1")

    def test_resume_nonexistent_raises_not_found(self):
        queue_repo = FakeQueueRepository()
        task_repo = FakeTaskRepository()

        with pytest.raises(NotFoundError):
            resume_task(queue_repo, task_repo, "missing")


class TestCancelTask:
    """cancel_task 单元测试。"""

    def test_cancel_queued_success(self):
        item = make_item("qi-1", QueueState.QUEUED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = cancel_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert result is item
        assert result.state == QueueState.CANCELLED
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_cancel_claimed_success(self):
        item = make_item(
            "qi-1", QueueState.CLAIMED, "worker-1", datetime(2026, 8, 6, 12, 0)
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = cancel_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert result.state == QueueState.CANCELLED
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_cancel_running_success(self):
        item = make_item(
            "qi-1", QueueState.RUNNING, "worker-1", datetime(2026, 8, 6, 12, 0)
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = cancel_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert result.state == QueueState.CANCELLED
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_cancel_terminal_raises_conflict(self):
        for state in (QueueState.COMPLETED, QueueState.CANCELLED):
            item = make_item("qi-1", state)
            queue_repo = FakeQueueRepository({"qi-1": item})
            task_repo = FakeTaskRepository()

            with pytest.raises(ConflictError):
                cancel_task(queue_repo, task_repo, "qi-1", "worker-1")

    def test_cancel_wrong_worker_raises_conflict(self):
        item = make_item("qi-1", QueueState.RUNNING, "worker-A")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            cancel_task(queue_repo, task_repo, "qi-1", "worker-B")

        assert item.state == QueueState.RUNNING
        assert item.claimed_by == "worker-A"

    def test_cancel_nonexistent_raises_not_found(self):
        queue_repo = FakeQueueRepository()
        task_repo = FakeTaskRepository()

        with pytest.raises(NotFoundError):
            cancel_task(queue_repo, task_repo, "missing", "worker-1")


class TestRetryTask:
    """retry_task 单元测试。"""

    def test_retry_manual_review_success(self):
        item = make_item(
            "qi-1",
            QueueState.MANUAL_REVIEW,
            "worker-1",
            datetime(2026, 8, 6, 12, 0),
            attempt_count=3,
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = retry_task(queue_repo, task_repo, "qi-1")

        assert result is item
        assert result.state == QueueState.QUEUED
        assert result.attempt_count == 0
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_retry_failed_success(self):
        item = make_item(
            "qi-1",
            QueueState.FAILED,
            "worker-1",
            datetime(2026, 8, 6, 12, 0),
            attempt_count=3,
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = retry_task(queue_repo, task_repo, "qi-1")

        assert result.state == QueueState.QUEUED
        assert result.attempt_count == 0
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_retry_retry_wait_success(self):
        item = make_item(
            "qi-1",
            QueueState.RETRY_WAIT,
            "worker-1",
            datetime(2026, 8, 6, 12, 0),
            attempt_count=2,
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = retry_task(queue_repo, task_repo, "qi-1")

        assert result.state == QueueState.QUEUED
        assert result.attempt_count == 0
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_retry_invalid_state_raises_conflict(self):
        item = make_item("qi-1", QueueState.QUEUED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            retry_task(queue_repo, task_repo, "qi-1")

    def test_retry_nonexistent_raises_not_found(self):
        queue_repo = FakeQueueRepository()
        task_repo = FakeTaskRepository()

        with pytest.raises(NotFoundError):
            retry_task(queue_repo, task_repo, "missing")


class TestTaskStatusSync:
    """队列控制操作联动更新 DramaTask 状态。"""

    def _task_repo(self, status: str) -> FakeTaskRepository:
        return FakeTaskRepository(
            {
                "task-1": DramaTask(
                    id="task-1",
                    drama_name="测试剧",
                    platform="TOMATO",
                    available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
                    status=status,
                )
            }
        )

    def test_pause_and_resume_sync_task_status(self):
        item = make_item("qi-1", QueueState.RUNNING, "worker-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = self._task_repo(TaskStatus.RUNNING)

        pause_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert task_repo.get("task-1").status == TaskStatus.RUNNING
        resume_task(queue_repo, task_repo, "qi-1")
        assert task_repo.get("task-1").status == TaskStatus.READY

    def test_cancel_syncs_task_status(self):
        item = make_item("qi-1", QueueState.QUEUED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = self._task_repo(TaskStatus.READY)

        cancel_task(queue_repo, task_repo, "qi-1", "worker-1")

        assert task_repo.get("task-1").status == TaskStatus.CANCELLED

    def test_retry_syncs_task_status(self):
        item = make_item(
            "qi-1", QueueState.MANUAL_REVIEW, "worker-1", attempt_count=2
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = self._task_repo(TaskStatus.MANUAL_REVIEW)

        retry_task(queue_repo, task_repo, "qi-1")

        assert task_repo.get("task-1").status == TaskStatus.READY

    def test_manual_review_syncs_task_status(self):
        item = make_item("qi-1", QueueState.RUNNING, "worker-1")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = self._task_repo(TaskStatus.RUNNING)

        mark_manual_review(queue_repo, task_repo, "qi-1", "worker-1")

        assert task_repo.get("task-1").status == TaskStatus.MANUAL_REVIEW


class TestMarkManualReview:
    """mark_manual_review 单元测试。"""

    def test_mark_claimed_success(self):
        item = make_item(
            "qi-1", QueueState.CLAIMED, "worker-1", datetime(2026, 8, 6, 12, 0)
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = mark_manual_review(queue_repo, task_repo, "qi-1", "worker-1")

        assert result is item
        assert result.state == QueueState.MANUAL_REVIEW
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_mark_running_success(self):
        item = make_item(
            "qi-1", QueueState.RUNNING, "worker-1", datetime(2026, 8, 6, 12, 0)
        )
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        result = mark_manual_review(queue_repo, task_repo, "qi-1", "worker-1")

        assert result.state == QueueState.MANUAL_REVIEW
        assert result.claimed_by is None
        assert result.lease_until is None

    def test_mark_wrong_worker_raises_conflict(self):
        item = make_item("qi-1", QueueState.CLAIMED, "worker-A")
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            mark_manual_review(queue_repo, task_repo, "qi-1", "worker-B")

        assert item.state == QueueState.CLAIMED
        assert item.claimed_by == "worker-A"

    def test_mark_invalid_state_raises_conflict(self):
        item = make_item("qi-1", QueueState.QUEUED)
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository()

        with pytest.raises(ConflictError):
            mark_manual_review(queue_repo, task_repo, "qi-1", "worker-1")

    def test_mark_nonexistent_raises_not_found(self):
        queue_repo = FakeQueueRepository()
        task_repo = FakeTaskRepository()

        with pytest.raises(NotFoundError):
            mark_manual_review(queue_repo, task_repo, "missing", "worker-1")

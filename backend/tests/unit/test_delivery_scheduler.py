"""delivery_scheduler 单元测试：fake 仓储 + 可注入 now_fn。"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timezone

from backend.application.services.delivery_scheduler import DeliveryScheduler
from backend.domain.common.timezones import SHANGHAI_TZ, UTC, as_utc
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.platforms.mock.mock_feishu import MockFeishuAdapter

SCAN_DAY = date(2026, 8, 8)


def _shanghai(
    day: date, hour: int, minute: int = 0
) -> datetime:
    """构造上海时区 aware 时间。"""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=SHANGHAI_TZ)


def _task(
    task_id: str,
    available_time: datetime,
    drama_name: str = "示例短剧",
) -> DramaTask:
    """构造测试用 DramaTask，task_id 即飞书行号。"""
    return DramaTask(
        id=task_id,
        sheet_row=int(task_id),
        drama_name=drama_name,
        platform="TOMATO",
        available_time=available_time,
        owner="测试",
        status=TaskStatus.WAITING_TIME,
    )


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


class RecordingFeishu(MockFeishuAdapter):
    """记录每次 fetch_tasks 扫描日的 Mock 飞书。"""

    def __init__(self, tasks: list[DramaTask] | None = None) -> None:
        super().__init__(tasks=tasks)
        self.fetched_days: list[date] = []

    def fetch_tasks(self, day: date) -> list[DramaTask]:
        self.fetched_days.append(day)
        return super().fetch_tasks(day)


class TestDeliveryScheduler:
    """DeliveryScheduler.tick 单元测试。"""

    def test_first_scan_creates_tasks_and_waiting_queue_items(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        tasks = [
            _task("2", _shanghai(SCAN_DAY, 10)),
            _task("3", _shanghai(SCAN_DAY, 22)),
        ]
        feishu = RecordingFeishu(tasks)
        task_repo = FakeTaskRepository()
        queue_repo = FakeQueueRepository()
        scheduler = DeliveryScheduler(
            feishu, task_repo, queue_repo, now_fn=lambda: now
        )

        result = scheduler.tick(now)

        assert result.day == SCAN_DAY
        assert result.created_tasks == 2
        assert result.updated_tasks == 0
        assert result.enqueued == 2
        assert result.skipped == 0
        assert feishu.fetched_days == [SCAN_DAY]
        assert set(task_repo._tasks) == {"2", "3"}
        assert all(
            task.status == TaskStatus.WAITING_TIME
            for task in task_repo._tasks.values()
        )
        assert len(queue_repo._items) == 2
        for task in tasks:
            items = queue_repo.list_by_task(task.id)
            assert len(items) == 1
            assert items[0].state == QueueState.WAITING_TIME
            assert items[0].available_at == as_utc(task.available_time)

    def test_second_scan_skips_existing_tasks_and_queue_items(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        task = _task("2", _shanghai(SCAN_DAY, 10))
        feishu = RecordingFeishu([task])
        task_repo = FakeTaskRepository()
        queue_repo = FakeQueueRepository()
        scheduler = DeliveryScheduler(
            feishu, task_repo, queue_repo, now_fn=lambda: now
        )

        first = scheduler.tick(now)
        queue_id = queue_repo.list_by_task(task.id)[0].id
        second = scheduler.tick(now)

        assert first.enqueued == 1
        assert second.created_tasks == 0
        assert second.updated_tasks == 1
        assert second.enqueued == 0
        assert second.skipped == 1
        assert len(queue_repo._items) == 1
        item = queue_repo.list_by_task(task.id)[0]
        assert item.id == queue_id
        assert item.state == QueueState.WAITING_TIME

    def test_completed_queue_item_is_not_auto_requeued(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        task = _task("2", _shanghai(SCAN_DAY, 10))
        task_repo = FakeTaskRepository({task.id: task})
        old_item = QueueItem(
            id="q-old",
            task_id=task.id,
            state=QueueState.COMPLETED,
            available_at=datetime(2020, 1, 1, tzinfo=UTC),
            claimed_by="worker-1",
            lease_until=datetime(2020, 1, 1, 1, 0, tzinfo=UTC),
            attempt_count=3,
        )
        queue_repo = FakeQueueRepository({"q-old": old_item})
        scheduler = DeliveryScheduler(
            RecordingFeishu([task]), task_repo, queue_repo, now_fn=lambda: now
        )

        result = scheduler.tick(now)

        assert result.enqueued == 0
        assert result.skipped == 1
        items = queue_repo.list_by_task(task.id)
        assert len(items) == 1
        assert items[0].id == "q-old"
        assert items[0].state == QueueState.COMPLETED
        assert items[0].claimed_by == "worker-1"

    def test_cancelled_queue_item_is_not_auto_requeued(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        task = _task("2", _shanghai(SCAN_DAY, 10))
        task_repo = FakeTaskRepository({task.id: task})
        old_item = QueueItem(
            id="q-cancelled",
            task_id=task.id,
            state=QueueState.CANCELLED,
            available_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        queue_repo = FakeQueueRepository({"q-cancelled": old_item})
        scheduler = DeliveryScheduler(
            RecordingFeishu([task]), task_repo, queue_repo, now_fn=lambda: now
        )

        result = scheduler.tick(now)

        assert result.enqueued == 0
        assert result.skipped == 1
        item = queue_repo.list_by_task(task.id)[0]
        assert item.state == QueueState.CANCELLED

    def test_task_available_time_is_normalized_to_utc(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        local_time = _shanghai(SCAN_DAY, 10)
        task = _task("2", local_time)
        scheduler = DeliveryScheduler(
            RecordingFeishu([task]),
            FakeTaskRepository(),
            FakeQueueRepository(),
            now_fn=lambda: now,
        )

        scheduler.tick(now)

        stored = scheduler._task_repo.get("2")
        assert stored.available_time == as_utc(local_time)
        assert stored.available_time.tzinfo is not None

    def test_available_time_update_syncs_queue_available_at(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        task = _task("2", _shanghai(SCAN_DAY, 10))
        feishu = RecordingFeishu([task])
        task_repo = FakeTaskRepository()
        queue_repo = FakeQueueRepository()
        scheduler = DeliveryScheduler(
            feishu, task_repo, queue_repo, now_fn=lambda: now
        )

        scheduler.tick(now)
        updated = _task("2", _shanghai(SCAN_DAY, 18))
        feishu._tasks = [updated]

        result = scheduler.tick(now)

        assert result.skipped == 1
        item = queue_repo.list_by_task(task.id)[0]
        assert item.state == QueueState.WAITING_TIME
        assert item.available_at == as_utc(updated.available_time)
        assert task_repo.get(task.id).available_time == as_utc(
            updated.available_time
        )

    def test_existing_queued_item_is_skipped_without_reset(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        task = _task("2", _shanghai(SCAN_DAY, 10))
        task_repo = FakeTaskRepository({task.id: task})
        queued_item = QueueItem(
            id="q-queued",
            task_id=task.id,
            state=QueueState.QUEUED,
            available_at=as_utc(task.available_time),
        )
        queue_repo = FakeQueueRepository({"q-queued": queued_item})
        scheduler = DeliveryScheduler(
            RecordingFeishu([task]), task_repo, queue_repo, now_fn=lambda: now
        )

        result = scheduler.tick(now)

        assert result.skipped == 1
        item = queue_repo.list_by_task(task.id)[0]
        assert item.id == "q-queued"
        assert item.state == QueueState.QUEUED
        assert item.available_at == as_utc(task.available_time)

    def test_run_forever_ticks_immediately_and_stops_on_event(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        scheduler = DeliveryScheduler(
            RecordingFeishu([]),
            FakeTaskRepository(),
            FakeQueueRepository(),
            now_fn=lambda: now,
            scan_interval_seconds=3600,
        )
        stop = threading.Event()
        ticked: list[datetime] = []
        original_tick = scheduler.tick

        def spy(now_value: datetime):
            ticked.append(now_value)
            return original_tick(now_value)

        scheduler.tick = spy
        thread = threading.Thread(
            target=scheduler.run_forever, args=(stop,), daemon=True
        )
        thread.start()
        try:
            deadline = time.monotonic() + 3
            while not ticked and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            stop.set()
            thread.join(timeout=3)

        assert ticked
        assert ticked[0] == now
        assert thread.is_alive() is False

    def test_run_forever_continues_after_tick_error(self):
        now = _shanghai(SCAN_DAY, 0, 30)
        scheduler = DeliveryScheduler(
            RecordingFeishu([]),
            FakeTaskRepository(),
            FakeQueueRepository(),
            now_fn=lambda: now,
            scan_interval_seconds=0.05,
        )
        stop = threading.Event()
        calls = {"count": 0}
        original_tick = scheduler.tick

        def flaky(now_value: datetime):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("boom")
            stop.set()
            return original_tick(now_value)

        scheduler.tick = flaky
        thread = threading.Thread(
            target=scheduler.run_forever, args=(stop,), daemon=True
        )
        thread.start()
        thread.join(timeout=3)

        assert calls["count"] >= 2
        assert thread.is_alive() is False

    def test_scan_day_uses_shanghai_local_date(self):
        # UTC 2026-08-07 16:30 = 上海 2026-08-08 00:30
        now = datetime(2026, 8, 7, 16, 30, tzinfo=UTC)
        task = _task("2", _shanghai(SCAN_DAY, 0, 30))
        feishu = RecordingFeishu([task])
        scheduler = DeliveryScheduler(
            feishu, FakeTaskRepository(), FakeQueueRepository(), now_fn=lambda: now
        )

        result = scheduler.tick(now)

        assert result.day == SCAN_DAY
        assert feishu.fetched_days == [SCAN_DAY]
        assert result.created_tasks == 1
        assert result.enqueued == 1

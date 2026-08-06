"""剧目扫描调度服务：同步飞书当天任务并自动入队。"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from backend.domain.common.timezones import SHANGHAI_TZ, as_utc
from backend.domain.ports.adapters import FeishuAdapter
from backend.domain.ports.repositories import QueueRepository, TaskRepository
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus

logger = logging.getLogger(__name__)

_TERMINAL_QUEUE_STATES = frozenset({QueueState.COMPLETED, QueueState.CANCELLED})


@dataclass(frozen=True)
class ScanResult:
    """一次扫描的增量统计。"""

    day: date
    created_tasks: int
    updated_tasks: int
    enqueued: int
    skipped: int


class DeliveryScheduler:
    """扫描飞书当天剧目，upsert DramaTask 并确保 WAITING_TIME 队列项。"""

    def __init__(
        self,
        feishu: FeishuAdapter,
        task_repo: TaskRepository,
        queue_repo: QueueRepository,
        now_fn: Callable[[], datetime] | None = None,
        scan_interval_seconds: int = 3600,
    ) -> None:
        self._feishu = feishu
        self._task_repo = task_repo
        self._queue_repo = queue_repo
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._scan_interval_seconds = scan_interval_seconds
        self._stop_event = threading.Event()

    @property
    def scan_interval_seconds(self) -> int:
        """调度扫描间隔（秒）。"""
        return self._scan_interval_seconds

    def tick(self, now: datetime) -> ScanResult:
        """同步一次“当天”任务，now 的上海本地日期决定扫描日。"""
        day = as_utc(now).astimezone(SHANGHAI_TZ).date()
        fetched = self._feishu.fetch_tasks(day)
        created = 0
        updated = 0
        enqueued = 0
        skipped = 0

        for source in fetched:
            existing = self._task_repo.get(source.id)
            if existing is None:
                self._task_repo.add(_new_task(source))
                created += 1
            else:
                _sync_task(existing, source)
                self._task_repo.update(existing)
                updated += 1

            if self._ensure_queue_item(source):
                enqueued += 1
            else:
                skipped += 1

        return ScanResult(
            day=day,
            created_tasks=created,
            updated_tasks=updated,
            enqueued=enqueued,
            skipped=skipped,
        )

    def run_forever(
        self, stop_event: threading.Event | None = None
    ) -> None:
        """立即 tick 一次，随后按间隔循环；stop_event 可中断。"""
        stop = stop_event or self._stop_event
        while not stop.is_set():
            try:
                self.tick(self._now_fn())
            except Exception:
                logger.exception("剧目扫描失败，等待下一轮")
            stop.wait(self._scan_interval_seconds)

    def _ensure_queue_item(self, task: DramaTask) -> bool:
        """确保任务存在 WAITING_TIME 队列项；返回是否创建/重置入队。"""
        items = self._queue_repo.list_by_task(task.id)
        active = next(
            (item for item in items if item.state not in _TERMINAL_QUEUE_STATES),
            None,
        )
        if active is not None:
            # 已有活动项：不重建状态；等待中的项同步最新投放时间
            if active.state == QueueState.WAITING_TIME:
                _sync_available_at(active, task)
                self._queue_repo.update(active)
            return False
        if items:
            _reset_queue_item(items[0], task)
            self._queue_repo.update(items[0])
        else:
            self._queue_repo.add(_new_queue_item(task))
        return True


def _new_task(source: DramaTask) -> DramaTask:
    """按飞书来源创建初始态任务。"""
    return DramaTask(
        id=source.id,
        sheet_row=source.sheet_row,
        drama_name=source.drama_name,
        platform=source.platform,
        available_time=source.available_time,
        owner=source.owner,
        status=TaskStatus.WAITING_TIME,
    )


def _sync_task(existing: DramaTask, source: DramaTask) -> None:
    """已有任务仅同步平台、投放时间，不覆盖运行状态。"""
    existing.platform = source.platform
    existing.available_time = source.available_time


def _sync_available_at(item: QueueItem, task: DramaTask) -> None:
    """等待中的队列项同步最新投放时间。"""
    item.available_at = as_utc(task.available_time)


def _reset_queue_item(item: QueueItem, task: DramaTask) -> None:
    """终态队列项复用并重置为 WAITING_TIME。"""
    item.state = QueueState.WAITING_TIME
    item.available_at = as_utc(task.available_time)
    item.claimed_by = None
    item.lease_until = None
    item.attempt_count = 0
    item.next_run_at = None


def _new_queue_item(task: DramaTask) -> QueueItem:
    """创建任务对应的 WAITING_TIME 队列项。"""
    return QueueItem(
        id=str(uuid.uuid4()),
        task_id=task.id,
        state=QueueState.WAITING_TIME,
        available_at=as_utc(task.available_time),
    )

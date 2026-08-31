"""剧目扫描调度服务：同步飞书当天任务并自动入队。"""
from __future__ import annotations

import logging
import threading
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

_TERMINAL_QUEUE_STATES = frozenset(
    {QueueState.COMPLETED, QueueState.CANCELLED, QueueState.DRY_RUN}
)


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
            existing = _find_existing_task(self._task_repo, source)
            if existing is None:
                task = self._task_repo.add(_new_task(source))
                created += 1
            else:
                _sync_task(existing, source)
                task = self._task_repo.update(existing)
                updated += 1

            if self._ensure_queue_item(task):
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
        """确保任务存在 WAITING_TIME 队列项；终态任务不自动重跑。"""
        items = self._queue_repo.list_by_task(task.id)
        if task.status == TaskStatus.DRY_RUN:
            # 演练终态必须由人工点击入队，避免扫描/重启后自动再次演练。
            return False
        active = next(
            (item for item in items if item.state not in _TERMINAL_QUEUE_STATES),
            None,
        )
        if active is not None:
            # 已有活动项：不重建状态；等待中的项仅在投放时间变化时同步
            if active.state == QueueState.WAITING_TIME:
                latest = as_utc(task.available_time)
                if as_utc(active.available_at) != latest:
                    active.available_at = latest
                    self._queue_repo.update(active)
            return False
        if any(item.state in _TERMINAL_QUEUE_STATES for item in items):
            # 已完成/取消任务不自动重跑，人工重试走 API enqueue
            return False
        self._queue_repo.add(_new_queue_item(task))
        return True


def _new_task(source: DramaTask) -> DramaTask:
    """按飞书来源创建初始态任务。"""
    return DramaTask(
        id=str(uuid.uuid4()) if source.source_key else source.id,
        source_key=source.source_key,
        sheet_row=source.sheet_row,
        drama_name=source.drama_name,
        platform=source.platform,
        available_time=as_utc(source.available_time),
        owner=source.owner,
        status=TaskStatus.WAITING_TIME,
        source_links=dict(source.source_links),
        link_set=dict(source.link_set),
        link_status=source.link_status,
    )


def _sync_task(existing: DramaTask, source: DramaTask) -> None:
    """已有任务仅同步平台、投放时间，不覆盖运行状态。"""
    existing.sheet_row = source.sheet_row
    existing.source_key = source.source_key or existing.source_key
    existing.drama_name = source.drama_name
    existing.platform = source.platform
    existing.available_time = as_utc(source.available_time)
    if existing.link_status != "VALIDATED":
        existing.source_links = dict(source.source_links)
    if source.link_status == "VALIDATED" and source.link_set:
        existing.link_set = dict(source.link_set)
        existing.link_status = "VALIDATED"


def _find_existing_task(task_repo: TaskRepository, source: DramaTask) -> DramaTask | None:
    """优先按 source_key 匹配，兜底按剧名+投放时间+平台匹配。"""
    finder = getattr(task_repo, "get_by_source_key", None)
    if source.source_key and callable(finder):
        task = finder(source.source_key)
        if task is not None:
            return task
    fallback = getattr(task_repo, "get_by_drama_and_time", None)
    if callable(fallback):
        task = fallback(
            source.drama_name, as_utc(source.available_time), source.platform
        )
        if task is not None:
            logger.warning(
                "source_key 未命中但按剧名+时间兜底匹配到已有任务 "
                "drama=%s available_time=%s source_key_old=%s source_key_new=%s",
                source.drama_name,
                source.available_time,
                task.source_key,
                source.source_key,
            )
            task.source_key = source.source_key
            return task
    return task_repo.get(source.id)


def _new_queue_item(task: DramaTask) -> QueueItem:
    """创建任务对应的 WAITING_TIME 队列项。"""
    return QueueItem(
        id=str(uuid.uuid4()),
        task_id=task.id,
        state=QueueState.WAITING_TIME,
        available_at=as_utc(task.available_time),
    )

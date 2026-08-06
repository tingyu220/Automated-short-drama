"""队列推进服务 —— 到点入队后原子领取."""
from __future__ import annotations

from datetime import datetime

from backend.application.services.queue_service import enqueue_when_ready
from backend.domain.ports.repositories import QueueRepository
from backend.domain.queue.queue_item import QueueItem, QueueState


def advance_queue(
    queue_repo: QueueRepository,
    now: datetime,
    worker_id: str,
    lease_seconds: int = 60,
) -> tuple[list[QueueItem], QueueItem | None]:
    """推进队列：到点项置为 QUEUED 并持久化，再领取 1 条并持久化。

    Args:
        queue_repo: QueueRepository 实现，需提供 claim_next 扩展方法
                    （SqlAlchemyQueueRepository 已实现原子领取）。
        now: 当前时间。
        worker_id: 领取任务的 worker。
        lease_seconds: 租约时长（秒）。

    Returns:
        (已入队列表, 领取项或 None)。
    """
    waiting_items = queue_repo.list_by_state(QueueState.WAITING_TIME)
    enqueued = enqueue_when_ready(waiting_items, now)
    for item in enqueued:
        queue_repo.update(item)

    claimed = queue_repo.claim_next(worker_id, lease_seconds, now)
    return enqueued, claimed

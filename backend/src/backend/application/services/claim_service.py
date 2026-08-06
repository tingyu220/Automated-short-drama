"""原子领取与释放服务."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.common.timezones import as_utc
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.ports.repositories import QueueRepository
from backend.domain.queue.queue_item import QueueItem, QueueState


def claim_next_task(
    queue_repo: QueueRepository,
    worker_id: str,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> QueueItem | None:
    """原子领取一个 QUEUED 任务，委托给 QueueRepository.claim_next。"""
    if now is None:
        now = datetime.now(timezone.utc)
    return queue_repo.claim_next(worker_id, lease_seconds, as_utc(now))


def release_claimed(
    queue_repo: QueueRepository,
    queue_item_id: str,
    worker_id: str,
) -> bool:
    """释放已领取的队列项，仅当 claimed_by 匹配时置回 QUEUED。

    Returns:
        True 表示成功释放。

    Raises:
        NotFoundError: 队列项不存在。
        ConflictError: claimed_by 与 worker_id 不匹配。
    """
    if queue_repo.release_claimed(queue_item_id, worker_id):
        return True

    item = queue_repo.get(queue_item_id)
    if item is None:
        raise NotFoundError(f"QueueItem {queue_item_id} not found")
    if item.claimed_by != worker_id:
        raise ConflictError(
            f"QueueItem {queue_item_id} 由 {item.claimed_by} 认领，"
            f"而非 {worker_id}"
        )
    raise ConflictError(
        f"QueueItem {queue_item_id} 状态 {item.state} 不允许释放"
    )

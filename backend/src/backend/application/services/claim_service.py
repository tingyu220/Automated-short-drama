"""原子领取与释放服务."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.domain.common.timezones import as_utc
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)


def claim_next_task(
    session: Session,
    worker_id: str,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> QueueItem | None:
    """原子领取一个 QUEUED 任务，委托给 QueueRepository.claim_next."""
    repo = SqlAlchemyQueueRepository(session)
    if now is None:
        now = datetime.now(timezone.utc)
    return repo.claim_next(worker_id, lease_seconds, as_utc(now))


def release_claimed(
    session: Session, queue_item_id: str, worker_id: str
) -> bool:
    """释放已领取的队列项，仅当 claimed_by 匹配时置回 QUEUED。

    Returns:
        True 表示成功释放。

    Raises:
        NotFoundError: 队列项不存在。
        ConflictError: claimed_by 与 worker_id 不匹配。
    """
    repo = SqlAlchemyQueueRepository(session)
    item = repo.get(queue_item_id)
    if item is None:
        raise NotFoundError(f"QueueItem {queue_item_id} not found")
    if item.claimed_by != worker_id:
        raise ConflictError(
            f"QueueItem {queue_item_id} 由 {item.claimed_by} 认领，"
            f"而非 {worker_id}"
        )

    item.state = QueueState.QUEUED
    item.claimed_by = None
    item.lease_until = None
    repo.update(item)
    return True

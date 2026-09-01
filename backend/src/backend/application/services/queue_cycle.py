"""队列推进服务 —— 过期清理 + 到点入队 + 原子领取."""
from __future__ import annotations

import logging
from datetime import datetime

from backend.application.services.claim_service import claim_next_task
from backend.application.services.queue_service import enqueue_when_ready
from backend.domain.ports.repositories import QueueRepository
from backend.domain.queue.queue_item import QueueItem, QueueState

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3


def advance_queue(
    queue_repo: QueueRepository,
    now: datetime,
    worker_id: str,
    lease_seconds: int = 60,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> tuple[list[QueueItem], QueueItem | None]:
    """推进队列：先清理过期租约，再到点入队，再领取 1 条。

    Args:
        queue_repo: QueueRepository 实现。
        now: 当前时间。
        worker_id: 领取任务的 worker。
        lease_seconds: 租约时长（秒）。
        max_attempts: 过期恢复最大重试次数，超限转 MANUAL_REVIEW。

    Returns:
        (已入队列表, 领取项或 None)。
    """
    # 1. 清理过期 CLAIMED/RUNNING 项
    requeued, manual = queue_repo.recover_expired(now, max_attempts)
    if requeued:
        logger.warning(
            "租约过期自动清理: %d 项回到 QUEUED (attempts+1)",
            len(requeued),
        )
    if manual:
        logger.warning(
            "租约过期自动清理: %d 项超重试上限转 MANUAL_REVIEW",
            len(manual),
        )

    # 2. 到点项入队
    waiting_items = queue_repo.list_by_state(QueueState.WAITING_TIME)
    enqueued = enqueue_when_ready(waiting_items, now)
    for item in enqueued:
        queue_repo.update(item)

    # 3. 领取下一条
    claimed = claim_next_task(queue_repo, worker_id, lease_seconds, now=now)
    return enqueued, claimed

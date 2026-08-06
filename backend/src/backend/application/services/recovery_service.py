"""Worker 崩溃恢复服务 —— 回收过期租约的队列项."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.domain.ports.repositories import QueueRepository
from backend.domain.queue.queue_item import QueueItem, QueueState


@dataclass
class RecoveryResult:
    """恢复操作结果."""

    requeued: list[QueueItem] = field(default_factory=list)
    manual_review: list[QueueItem] = field(default_factory=list)


def recover_expired(
    queue_repo: QueueRepository,
    now: datetime,
    max_attempts: int = 3,
) -> RecoveryResult:
    """恢复所有过期租约的队列项。

    查找 state in (CLAIMED, RUNNING) 且 lease_until < now 的项：
    - attempt_count+1 <= max_attempts → 回到 QUEUED，清空 claimed_by/lease_until
    - 否则 → 进入 MANUAL_REVIEW，清空 claimed_by/lease_until

    状态迁移使用 QueueStateMachine.transition，非法迁移抛 ConflictError。
    """
    requeued, manual_review = queue_repo.recover_expired(now, max_attempts)
    return RecoveryResult(requeued=requeued, manual_review=manual_review)

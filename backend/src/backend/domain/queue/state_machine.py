"""QueueItem 状态机 - 合法迁移白名单."""
from __future__ import annotations

from backend.domain.errors.domain_error import ConflictError


# 合法迁移白名单
_TRANSITIONS: dict[str, set[str]] = {
    "WAITING_TIME": {"QUEUED"},
    "QUEUED": {"CLAIMED"},
    "CLAIMED": {"RUNNING"},
    "RUNNING": {"COMPLETED", "RETRY_WAIT", "PAUSED", "MANUAL_REVIEW", "FAILED", "CANCELLED"},
    "RETRY_WAIT": {"QUEUED", "MANUAL_REVIEW"},
    "PAUSED": {"QUEUED", "RUNNING", "CANCELLED"},
    "MANUAL_REVIEW": {"QUEUED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "FAILED": set(),
}


class QueueStateMachine:
    """队列状态迁移机."""

    @staticmethod
    def can_transition(current: str, target: str) -> bool:
        """检查是否可以从 current 迁移到 target。"""
        return target in _TRANSITIONS.get(current, set())

    @staticmethod
    def transition(current: str, target: str) -> str:
        """执行状态迁移；非法迁移抛 ConflictError。"""
        if not QueueStateMachine.can_transition(current, target):
            raise ConflictError(
                f"非法状态迁移: {current} -> {target}",
                details={"current": current, "target": target},
            )
        return target

"""QueueItem 数据类与 QueueState 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class QueueState:
    """QueueItem 生命周期状态."""

    WAITING_TIME = "WAITING_TIME"
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    PAUSED = "PAUSED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class QueueItem:
    """任务队列项领域模型."""

    task_id: str
    state: str = QueueState.WAITING_TIME
    priority: int = 0
    available_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    claimed_by: str | None = None
    lease_until: datetime | None = None
    attempt_count: int = 0
    next_run_at: datetime | None = None
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

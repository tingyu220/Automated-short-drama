"""Worker 租约数据模型."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

STATUS_RUNNING = "RUNNING"
STATUS_STOPPED = "STOPPED"


@dataclass
class WorkerLease:
    """Worker 租约，记录心跳与租约到期时间."""

    worker_id: str
    host: str
    pid: int
    status: str
    heartbeat_at: datetime
    lease_until: datetime

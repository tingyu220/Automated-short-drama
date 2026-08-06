"""DramaTask 数据类与 TaskStatus 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class TaskStatus:
    """DramaTask 生命周期状态."""

    WAITING_TIME = "WAITING_TIME"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class DramaTask:
    """短剧投放任务领域模型."""

    drama_name: str
    platform: str  # TOMATO / JUBIAN
    available_time: datetime
    id: str = ""
    sheet_row: int | None = None
    owner: str | None = None
    status: str = TaskStatus.WAITING_TIME
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

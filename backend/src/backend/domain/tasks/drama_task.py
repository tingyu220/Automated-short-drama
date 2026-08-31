"""DramaTask 数据类与 TaskStatus 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.tasks.end_type import EndType


class TaskStatus:
    """DramaTask 生命周期状态."""

    WAITING_TIME = "WAITING_TIME"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"
    LINK_EXTRACTED = "LINK_EXTRACTED"
    LINK_READY = "LINK_READY"
    CANCELLED = "CANCELLED"


@dataclass
class DramaTask:
    """短剧投放任务领域模型."""

    drama_name: str
    platform: str  # TOMATO / JUBIAN
    available_time: datetime
    end_type: str = EndType.NATIVE  # NATIVE / MINIPROGRAM
    id: str = ""
    source_key: str = ""
    sheet_row: int | None = None
    owner: str | None = None
    status: str = TaskStatus.WAITING_TIME
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_links: dict[str, str] = field(default_factory=dict)
    link_set: dict[str, str] = field(default_factory=dict)
    link_status: str = "NOT_STARTED"
    current_stage: str = "WAITING_AVAILABLE_TIME"
    target_stage: str = "LINK_READY"
    delivery_drama_id: str = ""
    promotion_configs: dict[str, str] = field(default_factory=dict)
    confirmed_drama_match: ConfirmedDramaMatch | None = None

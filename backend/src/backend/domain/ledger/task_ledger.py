"""TaskLedger 数据类."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TaskLedger:
    """任务交付台账领域模型."""

    task_id: str
    drama_name: str
    platform: str
    album_id: str = ""
    product_id: str = ""
    external_task_id: str = ""
    task_name: str = ""
    final_status: str = ""
    rule_version: str = ""
    config_version: str = ""
    completed_at: datetime | None = None
    id: str = ""

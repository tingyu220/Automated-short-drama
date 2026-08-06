"""API 响应模型（Pydantic v2）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaskSummary(BaseModel):
    """任务列表摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    drama_name: str
    platform: str
    available_time: datetime
    status: str
    owner: str | None
    queue_state: str | None
    updated_at: datetime


class TaskDetail(TaskSummary):
    """任务详情：摘要 + 最新队列项与台账信息。"""

    queue_item_id: str | None
    attempt_count: int | None
    claimed_by: str | None
    lease_until: datetime | None
    ledger_id: str | None


class QueueItemView(BaseModel):
    """队列项视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    state: str
    priority: int
    available_at: datetime
    claimed_by: str | None
    lease_until: datetime | None
    attempt_count: int
    next_run_at: datetime | None

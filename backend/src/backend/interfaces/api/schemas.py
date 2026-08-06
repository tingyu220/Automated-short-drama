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


class RuleSetView(BaseModel):
    """规则集视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    name: str
    category: str
    status: str
    updated_at: datetime


class RuleVersionView(BaseModel):
    """规则版本视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    status: str
    published_at: datetime | None


class SimulationOutputView(BaseModel):
    """单个价格候选的模拟结果。"""

    candidate: float
    matched_rule_key: str | None
    target_price: float | None
    distance: float | None
    selection_reason: str


class SimulationResultView(BaseModel):
    """价格模拟结果视图。"""

    inputs: list[float]
    outputs: list[SimulationOutputView]


class LedgerView(BaseModel):
    """任务交付台账视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    drama_name: str
    platform: str
    final_status: str
    completed_at: datetime | None


class ExecutionEventView(BaseModel):
    """执行事件视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    event_type: str
    level: str
    message: str
    context_json: dict | None
    occurred_at: datetime


class ExecutionArtifactView(BaseModel):
    """执行产物视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    artifact_type: str
    path: str
    size_bytes: int
    step_run_id: str | None
    checksum: str | None
    created_at: datetime


class AccountOverviewView(BaseModel):
    """账户概览视图；V1 返回 not_configured 占位。"""

    sync_status: str
    last_synced_at: datetime | None
    accounts: list[dict]


class ExceptionView(BaseModel):
    """异常中心视图：ERROR 事件或 MANUAL_REVIEW 任务。"""

    id: str
    task_id: str
    level: str
    message: str
    occurred_at: datetime

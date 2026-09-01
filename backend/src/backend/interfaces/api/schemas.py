"""API 响应模型（Pydantic v2）。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TaskSummary(BaseModel):
    """任务列表摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    drama_name: str
    platform: str
    end_type: str = "NATIVE"
    available_time: datetime
    status: str
    owner: str | None
    queue_state: str | None
    current_stage: str
    target_stage: str
    updated_at: datetime


class TaskDetail(TaskSummary):
    """任务详情：摘要 + 最新队列项与台账信息。"""

    queue_item_id: str | None
    attempt_count: int | None
    claimed_by: str | None
    lease_until: datetime | None
    failure_code: str | None
    retry_safe: bool | None
    ledger_id: str | None
    link_set: dict[str, str]
    delivery_drama_id: str
    promotion_configs: dict[str, str]
    steps: list["StepRunView"]
    drama_match_candidates: list[dict] = []
    confirmed_drama_match: dict | None = None


class TaskEnqueueBody(BaseModel):
    """任务运行终点；本期只开放提链与链接搭建。"""

    target_stage: Literal["LINK_EXTRACTION", "LINK_READY"] = "LINK_READY"


class TaskCreateBody(BaseModel):
    """直接创建单个任务（如小程序产线手动输入剧目）。"""

    drama_name: str
    end_type: Literal["NATIVE", "MINIPROGRAM"] = "NATIVE"
    platform: str = "TOMATO"
    available_time: datetime | None = None


class DramaMatchConfirmationBody(BaseModel):
    """人工确认番茄候选的稳定定位。"""

    locator_key: str


class RuntimeEnvironmentUpdate(BaseModel):
    """切换自动化运行环境。"""

    mode: Literal["MOCK", "REAL"]
    confirm_real: bool = False


class OperatorMatchUpdate(BaseModel):
    """切换剧目匹配范围。"""

    match_group: bool


class RuntimeEnvironmentView(BaseModel):
    """运行环境与 Worker 生效状态。"""

    desired_mode: Literal["MOCK", "REAL"]
    worker_mode: Literal["MOCK", "REAL"] | None
    switching: bool
    operator_match_group: bool


class StepRunView(BaseModel):
    """任务阶段执行记录。"""

    model_config = ConfigDict(from_attributes=True)

    step_name: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    result_json: dict | None
    error_code: str | None
    error_message: str | None


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
    failure_code: str | None
    retry_safe: bool


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


class RuleVersionDetailView(BaseModel):
    """规则版本详情视图（含 payload）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    status: str
    published_at: datetime | None
    payload_json: dict


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
    sheet_row: int | None = None
    album_id: str = ""
    product_id: str = ""
    final_status: str
    completed_at: datetime | None
    task_name: str = ""
    external_task_id: str = ""
    rule_version: str = ""
    config_version: str = ""


class TemplatePriceRuleView(BaseModel):
    """IAP 模板价格规则视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    target_price: float
    min_price: float
    max_price: float
    same_distance_strategy: str
    enabled: bool


class MaterialRuleRangeView(BaseModel):
    """素材数量区间规则视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    min_material_count: int
    max_material_count: int | None
    strategy: str
    base_group_count: int
    copy_count: int
    group_size_cap: int
    target_project_count: int


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
    """账户概览视图；V1 使用内存 Mock 账户表。"""

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
    drama_name: str | None = None
    platform: str | None = None
    error_type: str | None = None
    step: str | None = None
    retry_count: int | None = None
    failure_code: str | None = None
    failure_details: dict | None = None
    retry_safe: bool | None = None
    screenshots: list[str] | None = None
    stack_trace: str | None = None


class DramaImportPreviewBody(BaseModel):
    """读取指定北京时间业务日的公用剧目。"""

    business_date: date
    operator_name: str = "田雨"


class DramaImportOperatorView(BaseModel):
    name: str
    group_prefix: str


class DramaImportConfirmBody(BaseModel):
    """确认一个已保存的导入预览。"""

    preview_id: str


class DramaImportRowView(BaseModel):
    """待写入私有表的一条剧目。"""

    source_row: int
    drama_name: str
    platform: str
    available_time: str
    has_validated_links: bool


class DramaImportErrorView(BaseModel):
    source_row: int
    message: str


class DramaImportPreviewView(BaseModel):
    preview_id: str
    business_date: date
    source_count: int
    new_count: int
    duplicate_count: int
    invalid_count: int
    rows: list[DramaImportRowView]
    errors: list[DramaImportErrorView]


class DramaImportRunView(BaseModel):
    run_id: str
    status: str
    business_date: date
    source_count: int
    new_count: int
    duplicate_count: int
    invalid_count: int
    inserted_count: int
    inserted_rows: list[int]
    verified: bool
    error_message: str | None


class ImportedDramaRecordView(BaseModel):
    source_key: str
    drama_name: str
    platform: str
    available_time: str
    operator_name: str
    task_id: str | None
    task_status: str | None


# ── MiniProgram ───────────────────────────────────────────


class MiniProgramTaskView(BaseModel):
    """MiniProgram 任务列表项。"""

    model_config = ConfigDict(from_attributes=True)

    task_id: str
    drama_name: str
    operator_name: str
    operator_code: str
    organization_group: str
    organization_path: str
    drama_short_name: str | None = None
    album_id: str | None = None
    workflow_status: str
    created_at: datetime
    updated_at: datetime


class MiniProgramConfigView(BaseModel):
    """MiniProgram 剧场配置视图。"""

    config_name: str
    mini_program: dict
    promotion: dict
    ocean: dict
    price_tiers: dict


class MiniProgramDiscoveryCaptureView(BaseModel):
    """单条 Discovery 捕获记录视图。"""

    url: str
    method: str
    status: int
    endpoint_type: str
    response_body: dict | list
    captured_at: str


class MiniProgramDiscoveryView(BaseModel):
    """Discovery 结果视图。"""

    task_id: str
    capture_count: int
    endpoint_counts: dict[str, int]
    endpoint_types: list[str]
    captures: list[MiniProgramDiscoveryCaptureView]
    artifacts_path: str | None = None

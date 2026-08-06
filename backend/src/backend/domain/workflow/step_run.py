"""StepRun 数据类与 StepStatus 常量."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class StepStatus:
    """StepRun 生命周期状态."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


@dataclass
class StepRun:
    """工作流步骤执行记录领域模型."""

    workflow_run_id: str
    step_name: str
    status: str = StepStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_json: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    id: str = ""

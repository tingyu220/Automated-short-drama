"""WorkflowRun 数据类."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class WorkflowRun:
    """投放工作流运行记录领域模型."""

    task_id: str
    status: str = "PENDING"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    id: str = ""

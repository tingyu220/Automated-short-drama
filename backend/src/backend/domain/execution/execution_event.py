"""执行事件领域模型与 EventLevel 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class EventLevel:
    """执行事件级别."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ExecutionEvent:
    """执行事件领域模型."""

    task_id: str
    event_type: str
    message: str
    level: str = EventLevel.INFO
    context_json: dict | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = ""

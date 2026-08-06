"""执行产物领域模型与 ArtifactType 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class ArtifactType:
    """执行产物类型."""

    SCREENSHOT = "SCREENSHOT"
    LOG = "LOG"
    HTML = "HTML"
    OTHER = "OTHER"


@dataclass
class ExecutionArtifact:
    """执行产物领域模型."""

    task_id: str
    artifact_type: str
    path: str
    size_bytes: int
    step_run_id: str | None = None
    checksum: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = ""

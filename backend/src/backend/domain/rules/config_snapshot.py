"""配置快照领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ConfigSnapshot:
    """任务执行时使用的配置快照领域模型."""

    task_id: str
    rule_version_id: str
    snapshot_json: dict
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

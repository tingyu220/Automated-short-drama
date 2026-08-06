"""配置变更审计领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ConfigChangeLog:
    """规则配置变更日志领域模型."""

    rule_set_id: str
    action: str
    actor: str
    from_version: str | None = None
    to_version: str | None = None
    detail_json: dict | None = None
    id: str = ""
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

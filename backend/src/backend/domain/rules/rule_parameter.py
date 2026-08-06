"""规则参数领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RuleParameter:
    """规则参数领域模型."""

    rule_version_id: str
    name: str
    value_json: dict
    data_type: str
    description: str = ""
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

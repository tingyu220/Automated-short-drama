"""规则版本领域模型与 RuleVersionStatus 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class RuleVersionStatus:
    """规则版本生命周期状态."""

    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


@dataclass
class RuleVersion:
    """规则版本领域模型."""

    rule_set_id: str
    version: str
    payload_json: dict
    id: str = ""
    status: str = RuleVersionStatus.DRAFT
    published_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

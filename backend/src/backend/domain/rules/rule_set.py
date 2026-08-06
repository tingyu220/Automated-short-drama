"""规则集领域模型与 RuleStatus 常量."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class RuleStatus:
    """规则集生命周期状态."""

    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


@dataclass
class RuleSet:
    """规则集领域模型."""

    key: str
    name: str
    category: str
    description: str = ""
    id: str = ""
    status: str = RuleStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

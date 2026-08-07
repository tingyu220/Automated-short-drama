"""素材数量区间规则领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class MaterialRuleRange:
    """素材数量区间规则领域模型."""

    min_material_count: int
    strategy: str
    base_group_count: int
    copy_count: int
    group_size_cap: int
    target_project_count: int
    key: str = ""
    max_material_count: int | None = None
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

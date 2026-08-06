"""标准投放计划规格领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PlanSpec:
    """标准投放计划规格（账户、CID、推广内容、产品库、命名）。"""

    drama_name: str
    platform: str
    task_name: str
    link_set: dict[str, str]  # IAA / 2.9 / 9.9
    account_cids: list[str]
    product_id: str | None = None
    rule_version: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

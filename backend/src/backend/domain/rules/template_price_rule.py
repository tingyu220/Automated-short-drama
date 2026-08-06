"""模板价格规则领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


class SameDistanceStrategy:
    """同距离模板排序策略."""

    HIGHER_PRICE_FIRST = "HIGHER_PRICE_FIRST"


@dataclass
class TemplatePriceRule:
    """IAP 模板价格规则领域模型."""

    target_price: float
    min_price: float
    max_price: float
    key: str = ""
    same_distance_strategy: str = SameDistanceStrategy.HIGHER_PRICE_FIRST
    enabled: bool = True
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

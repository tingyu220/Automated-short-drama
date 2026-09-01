"""统一链接采集结果。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.domain.assets.promotion_asset import PromotionAsset


class AcquisitionStatus:
    """一次采集的总体状态。"""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


@dataclass
class AcquisitionResult:
    """Provider 返回、验证器补全的统一结果。"""

    status: str
    expected_types: list[str] = field(default_factory=list)
    candidates: list[PromotionAsset] = field(default_factory=list)
    selected: list[PromotionAsset] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


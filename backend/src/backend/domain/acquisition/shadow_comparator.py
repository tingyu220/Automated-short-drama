"""Shadow Mode 对比器（Phase 7）。

对比 Legacy DOM 与 Network V2 的采集结果，记录差异：
- LEGACY_MISSING_V2_FOUND: Legacy 没找到但 V2 找到了
- LEGACY_FOUND_V2_MISSING: Legacy 找到了但 V2 没找到
- URL_MISMATCH: 同档位但 URL 不同（Critical）
- AMBIGUOUS: V2 返回歧义结果

Critical mismatch = 0 才能通过验收。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.domain.acquisition.acquisition_result import AcquisitionResult

logger = logging.getLogger(__name__)


class DiscrepancyType(Enum):
    """差异类型。"""

    LEGACY_MISSING_V2_FOUND = "LEGACY_MISSING_V2_FOUND"
    LEGACY_FOUND_V2_MISSING = "LEGACY_FOUND_V2_MISSING"
    URL_MISMATCH = "URL_MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class Discrepancy:
    """单条差异记录。"""

    type: DiscrepancyType
    link_type: str
    legacy_url: str = ""
    v2_url: str = ""
    is_critical: bool = False
    detail: str = ""


@dataclass
class ShadowComparison:
    """一次 Shadow 对比的完整结果。"""

    discrepancies: list[Discrepancy] = field(default_factory=list)

    @property
    def critical_mismatch_count(self) -> int:
        return sum(1 for d in self.discrepancies if d.is_critical)

    @property
    def is_passing(self) -> bool:
        return self.critical_mismatch_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "discrepancy_count": len(self.discrepancies),
            "critical_mismatch_count": self.critical_mismatch_count,
            "is_passing": self.is_passing,
            "discrepancies": [
                {
                    "type": d.type.value,
                    "link_type": d.link_type,
                    "legacy_url": d.legacy_url,
                    "v2_url": d.v2_url,
                    "is_critical": d.is_critical,
                    "detail": d.detail,
                }
                for d in self.discrepancies
            ],
        }


class ShadowComparator:
    """对比 Legacy DOM 与 Network V2 的采集结果。"""

    def compare(
        self,
        legacy: AcquisitionResult,
        v2: AcquisitionResult,
    ) -> ShadowComparison:
        """对比两个采集结果，返回差异列表。"""
        comparison = ShadowComparison()
        all_types = self._collect_all_types(legacy, v2)

        for link_type in all_types:
            legacy_asset = self._find_selected(legacy, link_type)
            v2_asset = self._find_selected(v2, link_type)
            v2_missing = link_type in v2.missing
            v2_ambiguous = v2.missing.get(link_type) == "AMBIGUOUS"

            # V2 歧义
            if v2_ambiguous:
                comparison.discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.AMBIGUOUS,
                        link_type=link_type,
                        legacy_url=legacy_asset.promotion_url if legacy_asset else "",
                        v2_url="",
                        is_critical=False,
                        detail=f"V2 returned AMBIGUOUS for {link_type}",
                    )
                )
                continue

            # Legacy 有、V2 没有
            if legacy_asset and not v2_asset:
                comparison.discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.LEGACY_FOUND_V2_MISSING,
                        link_type=link_type,
                        legacy_url=legacy_asset.promotion_url,
                        v2_url="",
                        is_critical=False,
                        detail=f"Legacy found {link_type} but V2 missing",
                    )
                )
                continue

            # Legacy 没有、V2 有
            if not legacy_asset and v2_asset:
                comparison.discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.LEGACY_MISSING_V2_FOUND,
                        link_type=link_type,
                        legacy_url="",
                        v2_url=v2_asset.promotion_url,
                        is_critical=False,
                        detail=f"V2 found {link_type} but Legacy missing",
                    )
                )
                continue

            # 都有 → 比较 URL
            if legacy_asset and v2_asset:
                if legacy_asset.promotion_url != v2_asset.promotion_url:
                    comparison.discrepancies.append(
                        Discrepancy(
                            type=DiscrepancyType.URL_MISMATCH,
                            link_type=link_type,
                            legacy_url=legacy_asset.promotion_url,
                            v2_url=v2_asset.promotion_url,
                            is_critical=True,
                            detail=f"URL mismatch for {link_type}",
                        )
                    )
                # URL 相同 → 无差异

        return comparison

    def _collect_all_types(
        self, legacy: AcquisitionResult, v2: AcquisitionResult
    ) -> set[str]:
        """收集两个结果中出现的所有档位类型。"""
        types: set[str] = set()
        for asset in legacy.selected:
            types.add(asset.link_type)
        for asset in v2.selected:
            types.add(asset.link_type)
        for asset in v2.candidates:
            types.add(asset.link_type)
        types.update(legacy.missing.keys())
        types.update(v2.missing.keys())
        return types

    def _find_selected(
        self, result: AcquisitionResult, link_type: str
    ):
        """在 selected 列表中找指定档位的资产。"""
        for asset in result.selected:
            if asset.link_type == link_type:
                return asset
        return None

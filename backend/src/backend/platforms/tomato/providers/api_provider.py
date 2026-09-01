"""番茄 API Provider（Phase 8）。

通过真实 API 接口查询和创建推广链接，
使用 CreateSafetyGuard 强制执行安全规则：

    Query → 不存在 → Create → 再次 Query → Validate

Provider 优先级：API Primary → Network Fallback → DOM Fallback → Manual

当前为接口层框架，等真实 API 接口确认后替换 TomatoApiClient 实现。
"""
from __future__ import annotations

import logging
import uuid
from typing import Protocol, runtime_checkable

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.create_safety_guard import (
    CreateOutcome,
    CreateSafetyGuard,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


@runtime_checkable
class TomatoApiClient(Protocol):
    """番茄平台 API 客户端协议。"""

    def query_promotions(
        self, drama_name: str, link_type: str
    ) -> list[PromotionAsset]: ...

    def create_promotion(
        self, drama_name: str, link_type: str
    ) -> PromotionAsset | None: ...


class ApiProvider:
    """通过 API 查询和创建推广链接。

    实现 PromotionProvider 协议。
    """

    def __init__(
        self,
        client: TomatoApiClient,
        price_rules: list[TemplatePriceRule],
        *,
        expected_types: list[str] | None = None,
    ) -> None:
        self._client = client
        self._price_rules = price_rules
        self._expected_types = expected_types or ["IAA", "2.9", "9.9"]
        self._guard = CreateSafetyGuard()

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """对每个预期档位执行 Query → Create → Requery → Validate。"""
        selected: list[PromotionAsset] = []
        candidates: list[PromotionAsset] = []
        missing: dict[str, str] = {}
        per_type: dict[str, dict] = {}

        for link_type in self._expected_types:
            result = self._guard.execute(
                link_type=link_type,
                query_fn=lambda lt: self._client.query_promotions(
                    task.drama_name, lt
                ),
                create_fn=lambda lt: self._client.create_promotion(
                    task.drama_name, lt
                ),
            )

            per_type[link_type] = {
                "outcome": result.outcome.value,
                "steps": [s.value for s in result.steps],
                "reason": result.reason,
            }

            if result.outcome == CreateOutcome.REUSED:
                asset = result.asset
                asset.acquisition_method = AcquisitionMethod.API
                asset.created_or_existing = CreationStatus.EXISTING
                selected.append(asset)
                candidates.append(asset)

            elif result.outcome == CreateOutcome.CREATED:
                asset = result.asset
                asset.acquisition_method = AcquisitionMethod.API
                asset.created_or_existing = CreationStatus.CREATED
                selected.append(asset)
                candidates.append(asset)

            elif result.outcome == CreateOutcome.AMBIGUOUS:
                missing[link_type] = "AMBIGUOUS"

            elif result.outcome == CreateOutcome.UNCERTAIN:
                missing[link_type] = "UNCERTAIN"

            elif result.outcome == CreateOutcome.NOT_FOUND:
                missing[link_type] = "NOT_FOUND"

        if not selected and not missing:
            status = AcquisitionStatus.NOT_FOUND
        elif missing:
            status = AcquisitionStatus.PARTIAL
        else:
            status = AcquisitionStatus.COMPLETE

        return AcquisitionResult(
            status=status,
            expected_types=list(selected_types(selected)) + list(missing.keys()),
            candidates=candidates,
            selected=selected,
            missing=missing,
            diagnostics={
                "api_provider": {
                    "provider": "API",
                    "per_type": per_type,
                    "query_call_count": len(self._expected_types),
                    "create_call_count": sum(
                        1 for lt in self._expected_types
                        if per_type.get(lt, {}).get("outcome") in ("CREATED", "UNCERTAIN")
                    ),
                }
            },
        )


def selected_types(selected: list[PromotionAsset]) -> set[str]:
    """获取已选资产的档位集合。"""
    return {a.link_type for a in selected}

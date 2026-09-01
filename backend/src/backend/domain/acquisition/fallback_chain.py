"""Provider 优先级链（Phase 8）。

按优先级依次尝试：API → Network → DOM → Manual

规则：
- 第一个找到某档位的 Provider 的结果被采用
- 后续 Provider 不覆盖已选中的档位
- 缺失的档位继续降级到下一个 Provider
- 全部 Provider 都没找到 → NOT_FOUND
"""
from __future__ import annotations

import logging
from typing import Any

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import PromotionAsset
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


class FallbackChainProvider:
    """按优先级链式调用 Provider。

    实现 PromotionProvider 协议。
    """

    def __init__(self, providers: list[Any]) -> None:
        self._providers = providers

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """按优先级链执行，合并各 Provider 结果。"""
        if not self._providers:
            return AcquisitionResult(
                status=AcquisitionStatus.NOT_FOUND,
                diagnostics={"fallback_chain": {"providers_tried": []}},
            )

        selected: list[PromotionAsset] = []
        selected_types: set[str] = set()
        candidates: list[PromotionAsset] = []
        missing: dict[str, str] = {}
        warnings: list[str] = []
        providers_tried: list[str] = []
        final_provider: str | None = None

        for provider in self._providers:
            name = _provider_name(provider)
            providers_tried.append(name)
            result = provider.acquire(task)

            for asset in result.candidates:
                if asset.link_type not in selected_types:
                    candidates.append(asset)

            for asset in result.selected:
                if asset.link_type not in selected_types:
                    selected.append(asset)
                    selected_types.add(asset.link_type)
                    final_provider = name

            for lt, reason in result.missing.items():
                if lt not in selected_types and lt not in missing:
                    missing[lt] = reason

            warnings.extend(result.warnings)

            # 如果 Provider 返回 COMPLETE，不再降级
            if result.status == AcquisitionStatus.COMPLETE:
                break

            all_types = {"IAA", "2.9", "9.9"}
            if selected_types >= all_types:
                break

        if not selected and not missing:
            status = AcquisitionStatus.NOT_FOUND
        elif missing:
            status = AcquisitionStatus.PARTIAL
        else:
            status = AcquisitionStatus.COMPLETE

        return AcquisitionResult(
            status=status,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=candidates,
            selected=selected,
            missing=missing,
            warnings=warnings,
            diagnostics={
                "fallback_chain": {
                    "providers_tried": providers_tried,
                    "final_provider": final_provider,
                    "selected_by_provider": {
                        a.link_type: final_provider
                        for a in selected
                    },
                }
            },
        )


def _provider_name(provider: Any) -> str:
    """获取 Provider 名称用于 diagnostics。"""
    # 优先使用 name 属性
    name_attr = getattr(provider, "name", None)
    if name_attr:
        return name_attr
    name = type(provider).__name__
    if "Api" in name or "API" in name:
        return "API"
    if "Network" in name:
        return "NETWORK"
    if "Dom" in name or "DOM" in name or "Legacy" in name:
        return "DOM"
    if "Manual" in name:
        return "MANUAL"
    return name

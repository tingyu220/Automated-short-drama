"""V2 Acquisition Pipeline（Phase 9）。

完整编排 V2 管线：
    Provider 链 acquire → Validator validate → 冻结 link_set → READY / MANUAL_REVIEW

流程：
    剧目到点
    ↓
    自动查询已有链接（API → Network → DOM）
    ↓
    自动创建缺失链接（CreateSafetyGuard）
    ↓
    验证 PromotionAsset
    ↓
    冻结 link_set
    ↓
    READY / MANUAL_REVIEW / FAILED
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.promotion_asset_validator import (
    PromotionAssetValidator,
)
from backend.domain.assets.promotion_asset import (
    AssetStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


class PipelineOutcome:
    """管线执行结果状态。"""

    READY = "READY"                  # 全部就绪，link_set 已冻结
    MANUAL_REVIEW = "MANUAL_REVIEW"  # 有歧义/验证失败/不确定
    FAILED = "FAILED"                # 全部缺失
    PARTIAL = "PARTIAL"              # 部分就绪


@dataclass
class PipelineResult:
    """V2 管线执行结果。"""

    status: str
    link_set: dict[str, str] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)
    per_type: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status == PipelineOutcome.READY


class V2AcquisitionPipeline:
    """V2 管线：Provider → Validator → 冻结 link_set。"""

    def __init__(
        self,
        provider: Any,
        *,
        validator: PromotionAssetValidator | None = None,
    ) -> None:
        self._provider = provider
        self._validator = validator or PromotionAssetValidator()

    def run(self, task: DramaTask) -> PipelineResult:
        """执行完整管线。"""
        # Step 1: Provider 采集
        raw_result = self._provider.acquire(task)

        # Step 2: Validator 验证
        validated = self._validator.validate(task, raw_result)

        # Step 3: 冻结 link_set（只含双重验证通过的资产）
        link_set = _freeze_link_set(validated)

        # Step 4: 构造 per_type 状态
        per_type = _build_per_type(validated)

        # Step 5: 确定整体状态
        status = _determine_status(validated, link_set)

        return PipelineResult(
            status=status,
            link_set=link_set,
            missing=dict(validated.missing),
            per_type=per_type,
            diagnostics={
                "acquisition_status": validated.status,
                "validated_count": len(validated.selected),
                "frozen_count": len(link_set),
                "missing": dict(validated.missing),
                "provider_diagnostics": dict(validated.diagnostics),
            },
        )


def _freeze_link_set(result: AcquisitionResult) -> dict[str, str]:
    """只冻结经过双重状态确认的唯一资产。"""
    return {
        asset.link_type: asset.promotion_url
        for asset in result.selected
        if asset.acquisition_status == AssetStatus.VALIDATED
        and asset.verification_status == VerificationStatus.VALIDATED
        and asset.promotion_url
    }


def _build_per_type(result: AcquisitionResult) -> dict[str, str]:
    """构造每个档位的状态。"""
    per_type: dict[str, str] = {}
    selected_types = {a.link_type for a in result.selected
                      if a.acquisition_status == AssetStatus.VALIDATED
                      and a.verification_status == VerificationStatus.VALIDATED}

    for link_type in result.expected_types:
        if link_type in selected_types:
            per_type[link_type] = "FOUND"
        elif link_type in result.missing:
            per_type[link_type] = result.missing[link_type]
        else:
            per_type[link_type] = "NOT_FOUND"

    return per_type


def _determine_status(
    result: AcquisitionResult,
    link_set: dict[str, str],
) -> str:
    """根据采集结果和冻结的 link_set 确定整体状态。"""
    if result.status == AcquisitionStatus.AMBIGUOUS:
        return PipelineOutcome.MANUAL_REVIEW

    # 有候选但全部验证失败 → 不是 NOT_FOUND，是 ACQUISITION_FAILED → MANUAL_REVIEW
    if result.status == AcquisitionStatus.FAILED and result.candidates and not link_set:
        return PipelineOutcome.MANUAL_REVIEW

    if result.status == AcquisitionStatus.NOT_FOUND and not link_set:
        return PipelineOutcome.FAILED

    # 所有预期档位都冻结成功
    all_expected = set(result.expected_types)
    if all_expected and all_expected <= set(link_set.keys()):
        return PipelineOutcome.READY

    if link_set:
        return PipelineOutcome.PARTIAL

    # 有 missing 但没有冻结成功 → 检查是否有验证失败
    if result.missing:
        return PipelineOutcome.MANUAL_REVIEW

    return PipelineOutcome.FAILED

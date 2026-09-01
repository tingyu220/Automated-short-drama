"""推广资产验证规则测试。"""
from __future__ import annotations

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
from datetime import datetime, timezone


def _task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )


def _asset(asset_id: str, link_type: str, url: str) -> PromotionAsset:
    return PromotionAsset(
        id=asset_id,
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type=link_type,
        promotion_url=url,
    )


def test_validator_selects_unique_valid_tomato_asset() -> None:
    candidate = _asset(
        "asset-1", "IAA", "aweme://playlet?advertise_param=abc"
    )
    result = PromotionAssetValidator().validate(
        _task(),
        AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA"],
            candidates=[candidate],
        ),
    )

    assert result.status == AcquisitionStatus.COMPLETE
    assert result.selected == [candidate]
    assert candidate.acquisition_status == AssetStatus.VALIDATED
    assert candidate.verification_status == VerificationStatus.VALIDATED


def test_validator_rejects_multiple_candidates_without_guessing() -> None:
    first = _asset("asset-1", "IAA", "aweme://playlet?advertise_param=one")
    second = _asset("asset-2", "IAA", "aweme://playlet?advertise_param=two")

    result = PromotionAssetValidator().validate(
        _task(),
        AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA"],
            candidates=[first, second],
        ),
    )

    assert result.status == AcquisitionStatus.AMBIGUOUS
    assert result.selected == []
    assert result.missing == {"IAA": "MULTIPLE_CANDIDATES"}
    assert all(
        asset.acquisition_status == AssetStatus.AMBIGUOUS
        for asset in (first, second)
    )


def test_validator_does_not_freeze_invalid_url() -> None:
    candidate = _asset("asset-1", "IAA", "https://example.com/not-playlet")

    result = PromotionAssetValidator().validate(
        _task(),
        AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA"],
            candidates=[candidate],
        ),
    )

    assert result.selected == []
    assert result.missing == {"IAA": "INVALID_URL"}
    assert candidate.acquisition_status == AssetStatus.FAILED
    assert candidate.verification_status == VerificationStatus.INVALID


def test_validator_rejects_candidate_for_another_drama() -> None:
    candidate = _asset(
        "asset-1", "IAA", "aweme://playlet?advertise_param=abc"
    )
    candidate.drama_name = "另一部剧"

    result = PromotionAssetValidator().validate(
        _task(),
        AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA"],
            candidates=[candidate],
        ),
    )

    assert result.selected == []
    assert result.missing == {"IAA": "DRAMA_IDENTITY_MISMATCH"}
    assert candidate.verification_status == VerificationStatus.INVALID

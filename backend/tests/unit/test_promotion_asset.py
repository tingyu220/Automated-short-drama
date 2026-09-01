"""PromotionAsset 与 AcquisitionResult 领域模型测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
    VerificationStatus,
)


def test_promotion_asset_keeps_business_identity_and_raw_data() -> None:
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    asset = PromotionAsset(
        id="asset-1",
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        external_drama_id="drama-1",
        link_type="IAA",
        promotion_url="aweme://playlet?advertise_param=abc",
        promotion_id="promotion-1",
        episode=2,
        acquisition_method=AcquisitionMethod.LEGACY,
        acquisition_status=AssetStatus.DISCOVERED,
        verification_status=VerificationStatus.UNVERIFIED,
        created_or_existing=CreationStatus.EXISTING,
        raw_data={"source_entry": "FREE"},
        created_at=now,
        updated_at=now,
    )

    assert asset.business_identity == (
        "TOMATO",
        "drama-1",
        "IAA",
        "episode:2",
    )
    assert asset.raw_data == {"source_entry": "FREE"}


def test_acquisition_result_defaults_to_empty_collections() -> None:
    result = AcquisitionResult(status=AcquisitionStatus.NOT_FOUND)

    assert result.expected_types == []
    assert result.candidates == []
    assert result.selected == []
    assert result.missing == {}
    assert result.warnings == []
    assert result.diagnostics == {}


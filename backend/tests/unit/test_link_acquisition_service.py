"""LinkAcquisitionService 编排测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.application.services.link_acquisition_service import (
    LinkAcquisitionService,
)
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
)
from backend.domain.tasks.drama_task import DramaTask


class StaticProvider:
    def __init__(self, result: AcquisitionResult) -> None:
        self.result = result

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        del task
        return self.result


class MemoryAssetRepository:
    def __init__(self) -> None:
        self.items: list[PromotionAsset] = []

    def save_all(self, assets: list[PromotionAsset]) -> list[PromotionAsset]:
        self.items.extend(assets)
        return assets


def _task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )


def test_service_validates_and_saves_all_candidates() -> None:
    valid = PromotionAsset(
        id="valid",
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type="IAA",
        promotion_url="aweme://playlet?advertise_param=valid",
    )
    repository = MemoryAssetRepository()
    service = LinkAcquisitionService(
        StaticProvider(
            AcquisitionResult(
                status=AcquisitionStatus.PARTIAL,
                expected_types=["IAA"],
                candidates=[valid],
            )
        ),
        PromotionAssetValidator(),
        repository,
    )

    result = service.acquire(_task())

    assert result.status == AcquisitionStatus.COMPLETE
    assert result.selected == [valid]
    assert repository.items == [valid]
    assert repository.items[0].acquisition_status == AssetStatus.VALIDATED


def test_service_snapshot_contains_only_validated_selected_assets() -> None:
    valid = PromotionAsset(
        id="valid",
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type="IAA",
        promotion_url="aweme://playlet?advertise_param=valid",
    )
    invalid = PromotionAsset(
        id="invalid",
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type="9.9",
        promotion_url="https://example.com/invalid",
    )
    service = LinkAcquisitionService(
        StaticProvider(
            AcquisitionResult(
                status=AcquisitionStatus.PARTIAL,
                expected_types=["IAA", "9.9"],
                candidates=[valid, invalid],
            )
        ),
        PromotionAssetValidator(),
        MemoryAssetRepository(),
    )

    result = service.acquire(_task())

    assert service.build_link_snapshot(result) == {
        "IAA": "aweme://playlet?advertise_param=valid"
    }


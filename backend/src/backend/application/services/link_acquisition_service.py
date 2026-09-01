"""推广链接采集、验证与持久化用例。"""
from __future__ import annotations

from backend.domain.acquisition.acquisition_result import AcquisitionResult
from backend.domain.acquisition.promotion_asset_validator import (
    PromotionAssetValidator,
)
from backend.domain.assets.promotion_asset import (
    AssetStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.ports.promotion_provider import PromotionProvider
from backend.domain.tasks.drama_task import DramaTask


class LinkAcquisitionService:
    """统一编排 Provider、验证器和资产仓储。"""

    def __init__(
        self,
        provider: PromotionProvider,
        validator: PromotionAssetValidator,
        asset_repository,
    ) -> None:
        self._provider = provider
        self._validator = validator
        self._asset_repository = asset_repository

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        result = self._provider.acquire(task)
        validated = self._validator.validate(task, result)
        self._asset_repository.save_all(validated.candidates)
        return validated

    @staticmethod
    def build_link_snapshot(result: AcquisitionResult) -> dict[str, str]:
        """只冻结经过双重状态确认的唯一资产。"""
        return {
            asset.link_type: asset.promotion_url
            for asset in result.selected
            if asset.acquisition_status == AssetStatus.VALIDATED
            and asset.verification_status == VerificationStatus.VALIDATED
            and asset.promotion_url
        }


class NullPromotionAssetRepository:
    """仅供未注入持久化依赖的兼容调用方使用。"""

    def save_all(self, assets: list[PromotionAsset]) -> list[PromotionAsset]:
        return assets


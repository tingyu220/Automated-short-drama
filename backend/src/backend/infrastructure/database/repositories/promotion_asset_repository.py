"""PromotionAsset SQLAlchemy 仓储实现。"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.assets.promotion_asset import (
    AssetStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.infrastructure.database.models.promotion_asset import (
    PromotionAssetRecord,
)


class SqlAlchemyPromotionAssetRepository:
    """持久化推广资产事实，不对缺失身份字段进行猜测合并。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, asset: PromotionAsset) -> PromotionAsset:
        record = self._session.get(PromotionAssetRecord, asset.id)
        if record is None:
            record = PromotionAssetRecord(id=asset.id)
            self._session.add(record)
        self._copy_to_record(asset, record)
        self._session.flush()
        return self._to_domain(record)

    def save_all(self, assets: list[PromotionAsset]) -> list[PromotionAsset]:
        return [self.save(asset) for asset in assets]

    def list_by_task(self, task_id: str) -> list[PromotionAsset]:
        return self._list(
            select(PromotionAssetRecord).where(
                PromotionAssetRecord.task_id == task_id
            )
        )

    def find_by_identity(
        self,
        *,
        source_platform: str,
        external_drama_id: str,
        link_type: str,
        episode: int | None = None,
        template_id: str | None = None,
    ) -> list[PromotionAsset]:
        if not external_drama_id:
            return []
        stmt = select(PromotionAssetRecord).where(
            PromotionAssetRecord.source_platform == source_platform,
            PromotionAssetRecord.external_drama_id == external_drama_id,
            PromotionAssetRecord.link_type == link_type,
        )
        if episode is not None:
            stmt = stmt.where(PromotionAssetRecord.episode == episode)
        if template_id is not None:
            stmt = stmt.where(PromotionAssetRecord.template_id == template_id)
        return self._list(stmt)

    def find_validated_by_task(self, task_id: str) -> list[PromotionAsset]:
        return self._list(
            select(PromotionAssetRecord).where(
                PromotionAssetRecord.task_id == task_id,
                PromotionAssetRecord.acquisition_status == AssetStatus.VALIDATED,
                PromotionAssetRecord.verification_status
                == VerificationStatus.VALIDATED,
            )
        )

    def list_ambiguous(self, task_id: str) -> list[PromotionAsset]:
        return self._list(
            select(PromotionAssetRecord).where(
                PromotionAssetRecord.task_id == task_id,
                PromotionAssetRecord.acquisition_status == AssetStatus.AMBIGUOUS,
            )
        )

    def mark_invalid(self, asset_id: str) -> None:
        record = self._session.get(PromotionAssetRecord, asset_id)
        if record is None:
            return
        record.acquisition_status = AssetStatus.FAILED
        record.verification_status = VerificationStatus.INVALID
        self._session.flush()

    def _list(self, stmt) -> list[PromotionAsset]:
        records = self._session.execute(
            stmt.order_by(PromotionAssetRecord.created_at, PromotionAssetRecord.id)
        ).scalars().all()
        return [self._to_domain(record) for record in records]

    @staticmethod
    def _copy_to_record(
        asset: PromotionAsset,
        record: PromotionAssetRecord,
    ) -> None:
        for name in (
            "task_id",
            "source_platform",
            "drama_name",
            "external_drama_id",
            "link_type",
            "promotion_url",
            "promotion_id",
            "episode",
            "template_id",
            "template_name",
            "price",
            "acquisition_method",
            "acquisition_status",
            "verification_status",
            "created_or_existing",
            "created_at",
            "updated_at",
        ):
            setattr(record, name, getattr(asset, name))
        record.raw_json = json.dumps(asset.raw_data, ensure_ascii=False)

    @staticmethod
    def _to_domain(record: PromotionAssetRecord) -> PromotionAsset:
        try:
            raw_data = json.loads(record.raw_json or "{}")
        except json.JSONDecodeError:
            raw_data = {}
        return PromotionAsset(
            id=record.id,
            task_id=record.task_id,
            source_platform=record.source_platform,
            drama_name=record.drama_name,
            external_drama_id=record.external_drama_id,
            link_type=record.link_type,
            promotion_url=record.promotion_url,
            promotion_id=record.promotion_id,
            episode=record.episode,
            template_id=record.template_id,
            template_name=record.template_name,
            price=record.price,
            acquisition_method=record.acquisition_method,
            acquisition_status=record.acquisition_status,
            verification_status=record.verification_status,
            created_or_existing=record.created_or_existing,
            raw_data=raw_data if isinstance(raw_data, dict) else {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


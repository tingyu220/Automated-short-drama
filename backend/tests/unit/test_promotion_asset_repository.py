"""PromotionAsset SQLAlchemy 仓储测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.domain.assets.promotion_asset import (
    AssetStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.repositories.promotion_asset_repository import (
    SqlAlchemyPromotionAssetRepository,
)


def _asset(
    asset_id: str,
    *,
    task_id: str = "task-1",
    link_type: str = "IAA",
    episode: int | None = 2,
    template_id: str | None = None,
    status: str = AssetStatus.DISCOVERED,
) -> PromotionAsset:
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    return PromotionAsset(
        id=asset_id,
        task_id=task_id,
        source_platform="TOMATO",
        drama_name="测试剧",
        external_drama_id="drama-1",
        link_type=link_type,
        promotion_url=f"aweme://playlet?advertise_param={asset_id}",
        promotion_id=f"promotion-{asset_id}",
        episode=episode,
        template_id=template_id,
        acquisition_status=status,
        verification_status=(
            VerificationStatus.VALIDATED
            if status == AssetStatus.VALIDATED
            else VerificationStatus.UNVERIFIED
        ),
        raw_data={"asset": asset_id},
        created_at=now,
        updated_at=now,
    )


def _repository() -> tuple[Session, SqlAlchemyPromotionAssetRepository]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    return session, SqlAlchemyPromotionAssetRepository(session)


def test_repository_round_trips_asset_and_raw_data() -> None:
    session, repository = _repository()
    try:
        repository.save(_asset("asset-1"))

        stored = repository.list_by_task("task-1")

        assert len(stored) == 1
        assert stored[0].promotion_id == "promotion-asset-1"
        assert stored[0].raw_data == {"asset": "asset-1"}
    finally:
        session.close()


def test_repository_finds_deterministic_iaa_identity() -> None:
    session, repository = _repository()
    try:
        repository.save_all([_asset("asset-1"), _asset("asset-2", episode=3)])

        stored = repository.find_by_identity(
            source_platform="TOMATO",
            external_drama_id="drama-1",
            link_type="IAA",
            episode=3,
        )

        assert [item.id for item in stored] == ["asset-2"]
    finally:
        session.close()


def test_repository_lists_validated_and_ambiguous_assets_separately() -> None:
    session, repository = _repository()
    try:
        repository.save_all(
            [
                _asset("validated", status=AssetStatus.VALIDATED),
                _asset("ambiguous", status=AssetStatus.AMBIGUOUS),
            ]
        )

        assert [
            item.id for item in repository.find_validated_by_task("task-1")
        ] == ["validated"]
        assert [item.id for item in repository.list_ambiguous("task-1")] == [
            "ambiguous"
        ]
    finally:
        session.close()


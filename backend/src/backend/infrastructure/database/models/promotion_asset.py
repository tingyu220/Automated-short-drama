"""推广资产 ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class PromotionAssetRecord(Base):
    """推广链接发现、验证及来源事实。"""

    __tablename__ = "promotion_asset"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    drama_name: Mapped[str] = mapped_column(String(256), nullable=False)
    external_drama_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    promotion_url: Mapped[str] = mapped_column(Text, nullable=False)
    promotion_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    acquisition_method: Mapped[str] = mapped_column(String(32), nullable=False)
    acquisition_status: Mapped[str] = mapped_column(String(32), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_or_existing: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


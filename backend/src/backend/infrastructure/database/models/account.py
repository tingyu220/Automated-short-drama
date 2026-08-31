"""账户分配历史 ORM 模型。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class AccountUsageRecord(Base):
    """同日 CID 占用事实；数据库唯一约束防止重复分配。"""

    __tablename__ = "account_usage"
    __table_args__ = (
        UniqueConstraint("usage_day", "cid", name="uq_account_usage_day_cid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    drama_name: Mapped[str] = mapped_column(String(256), nullable=False)
    usage_day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cid: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    sheet_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

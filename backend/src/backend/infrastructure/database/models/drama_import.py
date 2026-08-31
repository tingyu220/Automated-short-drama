"""剧目导入运行记录 ORM 模型。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class DramaImportRunRecord(Base):
    """预览确认与顶部插入的本地审计记录。"""

    __tablename__ = "drama_import_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'PREVIEWED'")
    )
    inserted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    inserted_rows_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

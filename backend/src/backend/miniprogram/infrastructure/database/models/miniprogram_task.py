"""MiniProgram 任务数据 ORM 模型。

独立表，与 Native 业务表完全隔离。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class MiniProgramTaskRecord(Base):
    """MiniProgram 任务数据。"""

    __tablename__ = "miniprogram_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
    drama_name: Mapped[str] = mapped_column(String(256), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_code: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_group: Mapped[str] = mapped_column(String(128), nullable=False)
    organization_path: Mapped[str] = mapped_column(String(256), nullable=False)
    drama_short_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    album_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workflow_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_STARTED"
    )
    extra_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

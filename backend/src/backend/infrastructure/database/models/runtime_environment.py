"""全局运行环境 ORM 模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class RuntimeEnvironmentRecord(Base):
    """运行环境单例记录。"""

    __tablename__ = "runtime_environment"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    desired_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MOCK", server_default=text("'MOCK'")
    )
    worker_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    operator_match_group: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

"""执行事件与产物 ORM 模型."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class ExecutionEventRecord(Base):
    """执行事件记录，表名 execution_event."""

    __tablename__ = "execution_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="INFO",
        server_default=text("'INFO'"),
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # 存储 JSON 字符串；domain 层使用 dict，ORM 层负责序列化/反序列化
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ExecutionArtifactRecord(Base):
    """执行产物记录，表名 execution_artifact."""

    __tablename__ = "execution_artifact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task.id"), nullable=False
    )
    step_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("step_run.id"), nullable=True
    )
    artifact_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="OTHER",
        server_default=text("'OTHER'"),
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

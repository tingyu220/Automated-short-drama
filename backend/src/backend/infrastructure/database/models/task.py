"""任务队列 ORM 模型."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.database.base import Base


class DramaTaskRecord(Base):
    """短剧投放任务记录，表名 drama_task."""

    __tablename__ = "drama_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sheet_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drama_name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    available_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="WAITING_TIME"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class QueueItemRecord(Base):
    """任务队列项记录，表名 queue_item."""

    __tablename__ = "queue_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="WAITING_TIME"
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WorkflowRunRecord(Base):
    """工作流运行记录，表名 workflow_run."""

    __tablename__ = "workflow_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StepRunRecord(Base):
    """工作流步骤执行记录，表名 step_run."""

    __tablename__ = "step_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_run.id"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskLedgerRecord(Base):
    """任务交付台账记录，表名 task_ledger."""

    __tablename__ = "task_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    drama_name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    album_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    product_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    external_task_id: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    task_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    final_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    config_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

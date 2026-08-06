"""DramaTask 仓储 SQLAlchemy 实现."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.database.models.task import DramaTaskRecord


class SqlAlchemyTaskRepository:
    """TaskRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, task: DramaTask) -> DramaTask:
        """新增任务."""
        record = DramaTaskRecord(
            id=task.id,
            sheet_row=task.sheet_row,
            drama_name=task.drama_name,
            platform=task.platform,
            available_time=task.available_time,
            owner=task.owner,
            status=task.status,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_domain(record)

    def get(self, task_id: str) -> DramaTask | None:
        """按主键查询."""
        record = self._session.get(DramaTaskRecord, task_id)
        if record is None:
            return None
        return self._to_domain(record)

    def update(self, task: DramaTask) -> DramaTask:
        """按 id 全量覆盖字段."""
        record = self._session.get(DramaTaskRecord, task.id)
        if record is None:
            raise ValueError(f"DramaTask {task.id} not found")
        record.sheet_row = task.sheet_row
        record.drama_name = task.drama_name
        record.platform = task.platform
        record.available_time = task.available_time
        record.owner = task.owner
        record.status = task.status
        self._session.flush()
        return self._to_domain(record)

    def list_by_state(self, state: str) -> list[DramaTask]:
        """按状态列出任务."""
        stmt = select(DramaTaskRecord).where(DramaTaskRecord.status == state)
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    def list_by_filters(
        self,
        *,
        platform: str | None = None,
        status: str | None = None,
        q: str | None = None,
        available_from: datetime | None = None,
        available_to: datetime | None = None,
    ) -> list[DramaTask]:
        """按筛选条件列出任务，按 available_time 降序。"""
        stmt = select(DramaTaskRecord)
        if platform:
            stmt = stmt.where(DramaTaskRecord.platform == platform)
        if status:
            stmt = stmt.where(DramaTaskRecord.status == status)
        if q:
            stmt = stmt.where(DramaTaskRecord.drama_name.like(f"%{q}%"))
        if available_from is not None:
            stmt = stmt.where(DramaTaskRecord.available_time >= available_from)
        if available_to is not None:
            stmt = stmt.where(DramaTaskRecord.available_time < available_to)
        stmt = stmt.order_by(
            DramaTaskRecord.available_time.desc(),
            DramaTaskRecord.id.desc(),
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    @staticmethod
    def _to_domain(record: DramaTaskRecord) -> DramaTask:
        """ORM → 领域模型."""
        return DramaTask(
            id=record.id,
            sheet_row=record.sheet_row,
            drama_name=record.drama_name,
            platform=record.platform,
            available_time=record.available_time,
            owner=record.owner,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

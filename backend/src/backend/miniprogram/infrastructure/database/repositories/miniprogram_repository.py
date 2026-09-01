"""MiniProgram 任务仓储 SQLAlchemy 实现。

严格隔离：只操作 miniprogram_task 表，
不读写 NativePromotionAsset、link_set 或 Native Workflow。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.miniprogram.domain.task_data import MiniProgramTaskData
from backend.miniprogram.infrastructure.database.models.miniprogram_task import (
    MiniProgramTaskRecord,
)


def _to_domain(record: MiniProgramTaskRecord) -> MiniProgramTaskData:
    """ORM 记录转领域实体。"""
    return MiniProgramTaskData(
        id=record.id,
        task_id=record.task_id,
        drama_name=record.drama_name,
        operator_name=record.operator_name,
        operator_code=record.operator_code,
        organization_group=record.organization_group,
        organization_path=record.organization_path,
        drama_short_name=record.drama_short_name,
        album_id=record.album_id,
        workflow_status=record.workflow_status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_record(data: MiniProgramTaskData) -> MiniProgramTaskRecord:
    """领域实体转 ORM 记录。"""
    return MiniProgramTaskRecord(
        id=data.id or str(uuid.uuid4()),
        task_id=data.task_id,
        drama_name=data.drama_name,
        operator_name=data.operator_name,
        operator_code=data.operator_code,
        organization_group=data.organization_group,
        organization_path=data.organization_path,
        drama_short_name=data.drama_short_name,
        album_id=data.album_id,
        workflow_status=data.workflow_status,
        created_at=data.created_at,
        updated_at=data.updated_at,
    )


class SqlAlchemyMiniProgramTaskRepository:
    """MiniProgram 任务仓储 SQLAlchemy 实现。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, task_data: MiniProgramTaskData) -> MiniProgramTaskData:
        """保存（新建或更新）任务数据。"""
        record = self._session.get(MiniProgramTaskRecord, task_data.id) if task_data.id else None

        if record is None:
            # 尝试按 task_id 查找已有记录
            existing = (
                self._session.query(MiniProgramTaskRecord)
                .filter_by(task_id=task_data.task_id)
                .first()
            )
            if existing:
                # 更新已有记录
                existing.drama_name = task_data.drama_name
                existing.operator_name = task_data.operator_name
                existing.operator_code = task_data.operator_code
                existing.organization_group = task_data.organization_group
                existing.organization_path = task_data.organization_path
                existing.drama_short_name = task_data.drama_short_name
                existing.album_id = task_data.album_id
                existing.workflow_status = task_data.workflow_status
                existing.updated_at = datetime.now(timezone.utc)
                self._session.flush()
                return _to_domain(existing)

            # 新建
            record = _to_record(task_data)
            if not record.id:
                record.id = str(uuid.uuid4())
            self._session.add(record)
            self._session.flush()
            return _to_domain(record)

        # 更新
        record.drama_name = task_data.drama_name
        record.operator_name = task_data.operator_name
        record.operator_code = task_data.operator_code
        record.organization_group = task_data.organization_group
        record.organization_path = task_data.organization_path
        record.drama_short_name = task_data.drama_short_name
        record.album_id = task_data.album_id
        record.workflow_status = task_data.workflow_status
        record.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return _to_domain(record)

    def get_by_task_id(self, task_id: str) -> MiniProgramTaskData | None:
        """按 task_id 查询。"""
        record = (
            self._session.query(MiniProgramTaskRecord)
            .filter_by(task_id=task_id)
            .first()
        )
        return _to_domain(record) if record else None

    def list_all(self) -> list[MiniProgramTaskData]:
        """列出全部 MiniProgram 任务，按更新时间倒序。"""
        records = (
            self._session.query(MiniProgramTaskRecord)
            .order_by(MiniProgramTaskRecord.updated_at.desc())
            .all()
        )
        return [_to_domain(r) for r in records]

    def update_status(
        self, task_id: str, status: str
    ) -> MiniProgramTaskData | None:
        """更新工作流状态。"""
        record = (
            self._session.query(MiniProgramTaskRecord)
            .filter_by(task_id=task_id)
            .first()
        )
        if record is None:
            return None
        record.workflow_status = status
        record.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return _to_domain(record)

    def delete(self, task_id: str) -> bool:
        """删除任务数据。"""
        record = (
            self._session.query(MiniProgramTaskRecord)
            .filter_by(task_id=task_id)
            .first()
        )
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

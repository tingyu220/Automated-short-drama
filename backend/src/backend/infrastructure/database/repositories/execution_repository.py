"""执行事件与产物查询仓储 SQLAlchemy 实现。"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.execution.execution_artifact import ExecutionArtifact
from backend.domain.execution.execution_event import ExecutionEvent
from backend.infrastructure.database.models.execution import (
    ExecutionArtifactRecord,
    ExecutionEventRecord,
)


class SqlAlchemyExecutionRepository:
    """ExecutionRepository 协议的 SQLAlchemy 适配器。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_event(self, event: ExecutionEvent) -> ExecutionEvent:
        """写入执行事件，id 缺省生成 UUID，context_json 序列化为 JSON 文本。"""
        record = ExecutionEventRecord(
            id=event.id or str(uuid.uuid4()),
            task_id=event.task_id,
            event_type=event.event_type,
            message=event.message,
            level=event.level,
            context_json=(
                json.dumps(event.context_json, ensure_ascii=False)
                if event.context_json is not None
                else None
            ),
            occurred_at=event.occurred_at,
            created_at=event.created_at,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_event(record)

    def list_events(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
    ) -> list[ExecutionEvent]:
        """按任务/级别筛选执行事件，按发生时间倒序。"""
        stmt = select(ExecutionEventRecord)
        if task_id is not None:
            stmt = stmt.where(ExecutionEventRecord.task_id == task_id)
        if level is not None:
            stmt = stmt.where(ExecutionEventRecord.level == level)
        stmt = stmt.order_by(
            ExecutionEventRecord.occurred_at.desc(),
            ExecutionEventRecord.id.desc(),
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_event(record) for record in records]

    def list_artifacts(
        self,
        *,
        task_id: str | None = None,
    ) -> list[ExecutionArtifact]:
        """按任务筛选执行产物，按创建时间倒序。"""
        stmt = select(ExecutionArtifactRecord)
        if task_id is not None:
            stmt = stmt.where(ExecutionArtifactRecord.task_id == task_id)
        stmt = stmt.order_by(
            ExecutionArtifactRecord.created_at.desc(),
            ExecutionArtifactRecord.id.desc(),
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_artifact(record) for record in records]

    def delete_artifact(self, artifact_id: str) -> None:
        """按 id 删除执行产物记录。"""
        record = self._session.get(ExecutionArtifactRecord, artifact_id)
        if record is not None:
            self._session.delete(record)

    @staticmethod
    def _to_event(record: ExecutionEventRecord) -> ExecutionEvent:
        """ORM → 领域模型。"""
        return ExecutionEvent(
            id=record.id,
            task_id=record.task_id,
            event_type=record.event_type,
            message=record.message,
            level=record.level,
            context_json=(
                json.loads(record.context_json)
                if record.context_json is not None
                else None
            ),
            occurred_at=record.occurred_at,
            created_at=record.created_at,
        )

    @staticmethod
    def _to_artifact(record: ExecutionArtifactRecord) -> ExecutionArtifact:
        """ORM → 领域模型。"""
        return ExecutionArtifact(
            id=record.id,
            task_id=record.task_id,
            artifact_type=record.artifact_type,
            path=record.path,
            size_bytes=record.size_bytes,
            step_run_id=record.step_run_id,
            checksum=record.checksum,
            created_at=record.created_at,
        )

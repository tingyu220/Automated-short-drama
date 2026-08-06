"""TaskLedger 仓储 SQLAlchemy 实现."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.ledger.task_ledger import TaskLedger
from backend.infrastructure.database.models.task import TaskLedgerRecord


class SqlAlchemyLedgerRepository:
    """LedgerRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, ledger: TaskLedger) -> TaskLedger:
        """新增台账记录."""
        record = TaskLedgerRecord(
            id=ledger.id,
            task_id=ledger.task_id,
            drama_name=ledger.drama_name,
            platform=ledger.platform,
            album_id=ledger.album_id,
            product_id=ledger.product_id,
            external_task_id=ledger.external_task_id,
            task_name=ledger.task_name,
            final_status=ledger.final_status,
            rule_version=ledger.rule_version,
            config_version=ledger.config_version,
            completed_at=ledger.completed_at,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_domain(record)

    def get(self, ledger_id: str) -> TaskLedger | None:
        """按主键查询."""
        record = self._session.get(TaskLedgerRecord, ledger_id)
        if record is None:
            return None
        return self._to_domain(record)

    def update(self, ledger: TaskLedger) -> TaskLedger:
        """按 id 全量覆盖字段."""
        record = self._session.get(TaskLedgerRecord, ledger.id)
        if record is None:
            raise ValueError(f"TaskLedger {ledger.id} not found")
        record.task_id = ledger.task_id
        record.drama_name = ledger.drama_name
        record.platform = ledger.platform
        record.album_id = ledger.album_id
        record.product_id = ledger.product_id
        record.external_task_id = ledger.external_task_id
        record.task_name = ledger.task_name
        record.final_status = ledger.final_status
        record.rule_version = ledger.rule_version
        record.config_version = ledger.config_version
        record.completed_at = ledger.completed_at
        self._session.flush()
        return self._to_domain(record)

    def list_by_task(self, task_id: str) -> list[TaskLedger]:
        """按关联任务查询台账."""
        stmt = (
            select(TaskLedgerRecord)
            .where(TaskLedgerRecord.task_id == task_id)
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    def list_all(self) -> list[TaskLedger]:
        """按完成时间倒序列出全部台账。"""
        stmt = select(TaskLedgerRecord).order_by(
            TaskLedgerRecord.completed_at.desc(),
            TaskLedgerRecord.id.desc(),
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    @staticmethod
    def _to_domain(record: TaskLedgerRecord) -> TaskLedger:
        """ORM → 领域模型."""
        return TaskLedger(
            id=record.id,
            task_id=record.task_id,
            drama_name=record.drama_name,
            platform=record.platform,
            album_id=record.album_id,
            product_id=record.product_id,
            external_task_id=record.external_task_id,
            task_name=record.task_name,
            final_status=record.final_status,
            rule_version=record.rule_version,
            config_version=record.config_version,
            completed_at=record.completed_at,
        )

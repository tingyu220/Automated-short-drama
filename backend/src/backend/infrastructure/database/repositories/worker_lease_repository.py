"""Worker 租约仓储 SQLAlchemy 实现。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from backend.domain.worker.worker_lease import (
    STATUS_RUNNING,
    STATUS_STOPPED,
    WorkerLease,
)
from backend.infrastructure.database.models.worker import WorkerLeaseRecord


class SqlAlchemyWorkerLeaseRepository:
    """WorkerLeaseRepository 协议的 SQLAlchemy 适配器。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire(
        self,
        worker_id: str,
        host: str,
        pid: int,
        lease_until: datetime,
        heartbeat_at: datetime,
    ) -> bool:
        """条件原子获取租约：自己的过期/停止记录可接管，其他活跃 Worker 拒绝。"""
        stmt = (
            update(WorkerLeaseRecord)
            .where(
                WorkerLeaseRecord.worker_id == worker_id,
                or_(
                    WorkerLeaseRecord.status != STATUS_RUNNING,
                    WorkerLeaseRecord.lease_until <= heartbeat_at,
                ),
            )
            .values(
                host=host,
                pid=pid,
                status=STATUS_RUNNING,
                heartbeat_at=heartbeat_at,
                lease_until=lease_until,
            )
        )
        if self._session.execute(stmt).rowcount > 0:
            self._session.flush()
            return True

        other_active = (
            self._session.query(WorkerLeaseRecord)
            .filter(
                WorkerLeaseRecord.status == STATUS_RUNNING,
                WorkerLeaseRecord.lease_until > heartbeat_at,
                WorkerLeaseRecord.worker_id != worker_id,
            )
            .first()
        )
        if other_active is not None:
            return False

        record = (
            self._session.query(WorkerLeaseRecord)
            .filter(WorkerLeaseRecord.worker_id == worker_id)
            .first()
        )
        if record is None:
            record = WorkerLeaseRecord(
                worker_id=worker_id,
                host=host,
                pid=pid,
                status=STATUS_RUNNING,
                heartbeat_at=heartbeat_at,
                lease_until=lease_until,
            )
            self._session.add(record)
        else:
            record.host = host
            record.pid = pid
            record.status = STATUS_RUNNING
            record.heartbeat_at = heartbeat_at
            record.lease_until = lease_until
        self._session.flush()
        return True

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        lease_until: datetime,
        heartbeat_at: datetime,
    ) -> WorkerLease:
        """upsert 并刷新租约。"""
        record = (
            self._session.query(WorkerLeaseRecord)
            .filter(WorkerLeaseRecord.worker_id == worker_id)
            .first()
        )
        if record is None:
            record = WorkerLeaseRecord(
                worker_id=worker_id,
                host=host,
                pid=pid,
                status=STATUS_RUNNING,
                heartbeat_at=heartbeat_at,
                lease_until=lease_until,
            )
            self._session.add(record)
        else:
            record.host = host
            record.pid = pid
            record.status = STATUS_RUNNING
            record.heartbeat_at = heartbeat_at
            record.lease_until = lease_until
        self._session.flush()
        return self._to_domain(record)

    def release(self, worker_id: str) -> bool:
        """释放租约，状态置 STOPPED。"""
        record = (
            self._session.query(WorkerLeaseRecord)
            .filter(WorkerLeaseRecord.worker_id == worker_id)
            .first()
        )
        if record is None:
            return False
        record.status = STATUS_STOPPED
        self._session.flush()
        return True

    def is_active(self, worker_id: str, now: datetime) -> bool:
        """检查租约是否仍有效。"""
        record = (
            self._session.query(WorkerLeaseRecord)
            .filter(
                WorkerLeaseRecord.worker_id == worker_id,
                WorkerLeaseRecord.status == STATUS_RUNNING,
                WorkerLeaseRecord.lease_until > now,
            )
            .first()
        )
        return record is not None

    def list_expired(self, now: datetime) -> list[WorkerLease]:
        """列出已过期租约。"""
        records = (
            self._session.query(WorkerLeaseRecord)
            .filter(WorkerLeaseRecord.lease_until < now)
            .all()
        )
        return [self._to_domain(record) for record in records]

    @staticmethod
    def _to_domain(record: WorkerLeaseRecord) -> WorkerLease:
        return WorkerLease(
            worker_id=record.worker_id,
            host=record.host,
            pid=record.pid,
            status=record.status,
            heartbeat_at=record.heartbeat_at,
            lease_until=record.lease_until,
        )

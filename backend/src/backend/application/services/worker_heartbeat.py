"""Worker 心跳与租约管理服务.

所有函数接受 SQLAlchemy Session 作为首个参数，由调用方管理事务边界.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.domain.worker.worker_lease import (
    STATUS_RUNNING,
    STATUS_STOPPED,
    WorkerLease,
)
from backend.infrastructure.database.models.worker import WorkerLeaseRecord


def _record_to_domain(record: WorkerLeaseRecord) -> WorkerLease:
    """ORM 记录转领域模型."""
    return WorkerLease(
        worker_id=record.worker_id,
        host=record.host,
        pid=record.pid,
        status=record.status,
        heartbeat_at=record.heartbeat_at,
        lease_until=record.lease_until,
    )


def _now() -> datetime:
    """获取当前时间，便于测试 mock."""
    return datetime.now()


def acquire_lease(
    session: Session,
    worker_id: str,
    host: str,
    pid: int,
    lease_seconds: int = 60,
) -> bool:
    """尝试获取 Worker 租约.

    若已有其他 RUNNING Worker 且租约未过期则返回 False；
    否则创建或覆盖租约并返回 True.
    """
    now = _now()
    existing = session.query(WorkerLeaseRecord).filter(
        WorkerLeaseRecord.status == STATUS_RUNNING,
        WorkerLeaseRecord.lease_until > now,
        WorkerLeaseRecord.worker_id != worker_id,
    ).first()

    if existing is not None:
        return False

    record = session.query(WorkerLeaseRecord).filter(
        WorkerLeaseRecord.worker_id == worker_id,
    ).first()

    lease_until = now + timedelta(seconds=lease_seconds)

    if record is None:
        record = WorkerLeaseRecord(
            worker_id=worker_id,
            host=host,
            pid=pid,
            status=STATUS_RUNNING,
            heartbeat_at=now,
            lease_until=lease_until,
        )
        session.add(record)
    else:
        record.host = host
        record.pid = pid
        record.status = STATUS_RUNNING
        record.heartbeat_at = now
        record.lease_until = lease_until

    session.flush()
    return True


def heartbeat(
    session: Session,
    worker_id: str,
    host: str,
    pid: int,
    lease_seconds: int = 60,
) -> WorkerLease:
    """发送心跳，upsert 并刷新 heartbeat_at / lease_until."""
    now = _now()
    record = session.query(WorkerLeaseRecord).filter(
        WorkerLeaseRecord.worker_id == worker_id,
    ).first()

    lease_until = now + timedelta(seconds=lease_seconds)

    if record is None:
        record = WorkerLeaseRecord(
            worker_id=worker_id,
            host=host,
            pid=pid,
            status=STATUS_RUNNING,
            heartbeat_at=now,
            lease_until=lease_until,
        )
        session.add(record)
    else:
        record.host = host
        record.pid = pid
        record.status = STATUS_RUNNING
        record.heartbeat_at = now
        record.lease_until = lease_until

    session.flush()
    return _record_to_domain(record)


def release_lease(session: Session, worker_id: str) -> bool:
    """释放租约，将状态置为 STOPPED."""
    record = session.query(WorkerLeaseRecord).filter(
        WorkerLeaseRecord.worker_id == worker_id,
    ).first()

    if record is None:
        return False

    record.status = STATUS_STOPPED
    session.flush()
    return True


def is_lease_active(session: Session, worker_id: str) -> bool:
    """检查租约是否仍有效."""
    now = _now()
    record = session.query(WorkerLeaseRecord).filter(
        WorkerLeaseRecord.worker_id == worker_id,
        WorkerLeaseRecord.status == STATUS_RUNNING,
        WorkerLeaseRecord.lease_until > now,
    ).first()
    return record is not None


def list_expired_leases(
    session: Session,
    now: datetime | None = None,
) -> list[WorkerLease]:
    """列出已过期的租约（lease_until < now）."""
    now = now or _now()
    records = session.query(WorkerLeaseRecord).filter(
        WorkerLeaseRecord.lease_until < now,
    ).all()
    return [_record_to_domain(r) for r in records]

"""Worker 心跳与租约管理服务（仓储协议注入）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.domain.common.timezones import as_utc
from backend.domain.ports.repositories import WorkerLeaseRepository
from backend.domain.worker.worker_lease import WorkerLease


def _now() -> datetime:
    """获取当前 UTC 时间，便于测试 mock。"""
    return datetime.now(timezone.utc)


def acquire_lease(
    lease_repo: WorkerLeaseRepository,
    worker_id: str,
    host: str,
    pid: int,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> bool:
    """尝试获取 Worker 租约，条件由仓储原子执行。"""
    now = as_utc(now if now is not None else _now())
    return lease_repo.acquire(
        worker_id,
        host,
        pid,
        now + timedelta(seconds=lease_seconds),
        now,
    )


def heartbeat(
    lease_repo: WorkerLeaseRepository,
    worker_id: str,
    host: str,
    pid: int,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> WorkerLease:
    """发送心跳，由仓储 upsert 租约。"""
    now = as_utc(now if now is not None else _now())
    return lease_repo.heartbeat(
        worker_id,
        host,
        pid,
        now + timedelta(seconds=lease_seconds),
        now,
    )


def release_lease(
    lease_repo: WorkerLeaseRepository,
    worker_id: str,
) -> bool:
    """释放租约。"""
    return lease_repo.release(worker_id)


def is_lease_active(
    lease_repo: WorkerLeaseRepository,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    """检查租约是否仍有效。"""
    return lease_repo.is_active(
        worker_id,
        as_utc(now if now is not None else _now()),
    )


def list_expired_leases(
    lease_repo: WorkerLeaseRepository,
    now: datetime | None = None,
) -> list[WorkerLease]:
    """列出已过期租约。"""
    return lease_repo.list_expired(
        as_utc(now if now is not None else _now())
    )

"""WorkerHeartbeat 服务单元测试，使用 fake 租约仓储。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.services.worker_heartbeat import (
    acquire_lease,
    heartbeat,
    is_lease_active,
    list_expired_leases,
    release_lease,
    _now,
)
from backend.domain.worker.worker_lease import (
    STATUS_RUNNING,
    STATUS_STOPPED,
    WorkerLease,
)

FIXED_NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)


def _lease(
    worker_id: str = "w1",
    status: str = STATUS_RUNNING,
    lease_until: datetime | None = None,
) -> WorkerLease:
    return WorkerLease(
        worker_id=worker_id,
        host="localhost",
        pid=1234,
        status=status,
        heartbeat_at=FIXED_NOW,
        lease_until=lease_until or (FIXED_NOW + timedelta(seconds=60)),
    )


class FakeWorkerLeaseRepository:
    """内存 WorkerLeaseRepository 假实现。"""

    def __init__(
        self,
        records: dict[str, WorkerLease] | None = None,
    ) -> None:
        self._records = records or {}

    def acquire(
        self,
        worker_id: str,
        host: str,
        pid: int,
        lease_until: datetime,
        heartbeat_at: datetime,
    ) -> bool:
        if any(
            record.worker_id != worker_id
            and record.status == STATUS_RUNNING
            and record.lease_until > heartbeat_at
            for record in self._records.values()
        ):
            return False
        current = self._records.get(worker_id)
        self._records[worker_id] = WorkerLease(
            worker_id=worker_id,
            host=host,
            pid=pid,
            status=STATUS_RUNNING,
            heartbeat_at=heartbeat_at,
            lease_until=lease_until,
        )
        return True

    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        lease_until: datetime,
        heartbeat_at: datetime,
    ) -> WorkerLease:
        record = WorkerLease(
            worker_id=worker_id,
            host=host,
            pid=pid,
            status=STATUS_RUNNING,
            heartbeat_at=heartbeat_at,
            lease_until=lease_until,
        )
        self._records[worker_id] = record
        return record

    def release(self, worker_id: str) -> bool:
        record = self._records.get(worker_id)
        if record is None:
            return False
        record.status = STATUS_STOPPED
        return True

    def is_active(self, worker_id: str, now: datetime) -> bool:
        record = self._records.get(worker_id)
        return (
            record is not None
            and record.status == STATUS_RUNNING
            and record.lease_until > now
        )

    def list_expired(self, now: datetime) -> list[WorkerLease]:
        return [
            record
            for record in self._records.values()
            if record.lease_until < now
        ]


class TestAcquireLease:
    """acquire_lease 测试。"""

    def test_acquire_when_no_existing_lease(self):
        repo = FakeWorkerLeaseRepository()
        result = acquire_lease(
            repo, "w1", "host1", 100, 60, now=FIXED_NOW
        )
        assert result is True
        assert repo._records["w1"].status == STATUS_RUNNING

    def test_acquire_rejected_when_other_active(self):
        repo = FakeWorkerLeaseRepository(
            {"w1": _lease("w1", lease_until=FIXED_NOW + timedelta(seconds=10))}
        )
        result = acquire_lease(
            repo, "w2", "host2", 200, 60, now=FIXED_NOW
        )
        assert result is False

    def test_acquire_overwrite_own_expired_lease(self):
        repo = FakeWorkerLeaseRepository(
            {"w1": _lease("w1", lease_until=FIXED_NOW - timedelta(seconds=1))}
        )
        result = acquire_lease(
            repo, "w1", "host1", 100, 60, now=FIXED_NOW
        )
        assert result is True
        assert repo._records["w1"].lease_until > FIXED_NOW


class TestHeartbeat:
    """heartbeat 测试。"""

    def test_heartbeat_extends_lease(self):
        repo = FakeWorkerLeaseRepository(
            {"w1": _lease("w1", lease_until=FIXED_NOW)}
        )
        result = heartbeat(
            repo, "w1", "host1", 100, 60, now=FIXED_NOW
        )
        assert result.worker_id == "w1"
        assert result.status == STATUS_RUNNING
        assert result.lease_until > FIXED_NOW

    def test_heartbeat_creates_new_if_not_exists(self):
        repo = FakeWorkerLeaseRepository()
        result = heartbeat(
            repo, "w1", "host1", 100, 60, now=FIXED_NOW
        )
        assert result.worker_id == "w1"
        assert repo._records["w1"].worker_id == "w1"


class TestReleaseLease:
    """release_lease 测试。"""

    def test_release_existing_lease(self):
        repo = FakeWorkerLeaseRepository({"w1": _lease("w1")})
        assert release_lease(repo, "w1") is True
        assert repo._records["w1"].status == STATUS_STOPPED

    def test_release_nonexistent_lease(self):
        repo = FakeWorkerLeaseRepository()
        assert release_lease(repo, "nonexistent") is False


class TestIsLeaseActive:
    """is_lease_active 测试。"""

    def test_active_lease(self):
        repo = FakeWorkerLeaseRepository({"w1": _lease("w1")})
        assert is_lease_active(repo, "w1", now=FIXED_NOW) is True

    def test_no_active_lease(self):
        repo = FakeWorkerLeaseRepository()
        assert is_lease_active(repo, "w1", now=FIXED_NOW) is False


class TestListExpiredLeases:
    """list_expired_leases 测试。"""

    def test_returns_expired_only(self):
        repo = FakeWorkerLeaseRepository(
            {
                "w1": _lease(
                    "w1",
                    lease_until=FIXED_NOW - timedelta(seconds=1),
                ),
                "w2": _lease("w2"),
            }
        )
        result = list_expired_leases(repo, now=FIXED_NOW)
        assert [item.worker_id for item in result] == ["w1"]


class TestNow:
    """_now 时区语义测试。"""

    def test_now_is_aware_utc(self):
        now = _now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

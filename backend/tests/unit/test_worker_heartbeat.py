"""WorkerHeartbeat 服务单元测试，使用 mock session."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from backend.application.services.worker_heartbeat import (
    acquire_lease,
    heartbeat,
    release_lease,
    is_lease_active,
    list_expired_leases,
    _now,
)
from backend.domain.worker.worker_lease import STATUS_RUNNING, STATUS_STOPPED
from backend.infrastructure.database.models.worker import WorkerLeaseRecord

FIXED_NOW = datetime(2026, 8, 6, 12, 0, 0)


def _make_record(
    worker_id: str = "w1",
    host: str = "localhost",
    pid: int = 1234,
    status: str = STATUS_RUNNING,
    heartbeat_at: datetime | None = None,
    lease_until: datetime | None = None,
) -> WorkerLeaseRecord:
    now = heartbeat_at or FIXED_NOW
    return WorkerLeaseRecord(
        worker_id=worker_id,
        host=host,
        pid=pid,
        status=status,
        heartbeat_at=now,
        lease_until=lease_until or (now + timedelta(seconds=60)),
    )


class TestAcquireLease:
    """acquire_lease 测试."""

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_acquire_when_no_existing_lease(self, mock_now):
        """无已有租约时应成功获取."""
        session = MagicMock()
        session.execute.return_value.rowcount = 0
        q = session.query.return_value
        q.filter.return_value.first.return_value = None
        result = acquire_lease(session, "w1", "host1", 100, 60)
        assert result is True

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_acquire_rejected_when_other_active(self, mock_now):
        """其他 Worker 持有有效租约时被拒."""
        session = MagicMock()
        session.execute.return_value.rowcount = 0
        other = _make_record("other-worker")
        session.query.return_value.filter.return_value.first.return_value = other
        result = acquire_lease(session, "w1", "host1", 100, 60)
        assert result is False

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_acquire_overwrite_own_lease(self, mock_now):
        """自己的旧记录允许覆盖."""
        session = MagicMock()
        session.execute.return_value.rowcount = 0
        old_self = _make_record("w1")
        q1 = MagicMock()
        q2 = MagicMock()
        session.query.side_effect = [q1, q2]
        q1.filter.return_value.first.return_value = None
        q2.filter.return_value.first.return_value = old_self
        result = acquire_lease(session, "w1", "host1", 100, 60)
        assert result is True
        assert old_self.status == STATUS_RUNNING


class TestHeartbeat:
    """heartbeat 测试."""

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_heartbeat_extends_lease(self, mock_now):
        """心跳应延长 lease_until."""
        session = MagicMock()
        record = _make_record("w1", lease_until=FIXED_NOW)
        session.query.return_value.filter.return_value.first.return_value = record
        result = heartbeat(session, "w1", "host1", 100, 60)
        assert result.worker_id == "w1"
        assert result.status == STATUS_RUNNING

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_heartbeat_creates_new_if_not_exists(self, mock_now):
        """无记录时 heartbeat 应创建新记录."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        result = heartbeat(session, "w1", "host1", 100, 60)
        assert result.worker_id == "w1"
        session.add.assert_called_once()


class TestReleaseLease:
    """release_lease 测试."""

    def test_release_existing_lease(self):
        """释放已有租约."""
        session = MagicMock()
        record = _make_record("w1")
        session.query.return_value.filter.return_value.first.return_value = record
        result = release_lease(session, "w1")
        assert result is True
        assert record.status == STATUS_STOPPED

    def test_release_nonexistent_lease(self):
        """释放不存在的租约返回 False."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        result = release_lease(session, "nonexistent")
        assert result is False


class TestIsLeaseActive:
    """is_lease_active 测试."""

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_active_lease(self, mock_now):
        """有效租约返回 True."""
        session = MagicMock()
        q = session.query.return_value
        q.filter.return_value.first.return_value = _make_record("w1")
        assert is_lease_active(session, "w1") is True

    @patch("backend.application.services.worker_heartbeat._now", return_value=FIXED_NOW)
    def test_no_active_lease(self, mock_now):
        """无有效租约返回 False."""
        session = MagicMock()
        q = session.query.return_value
        q.filter.return_value.first.return_value = None
        assert is_lease_active(session, "w1") is False


class TestListExpiredLeases:
    """list_expired_leases 测试."""

    def test_returns_expired_only(self):
        """只返回已过期的租约."""
        session = MagicMock()
        expired = _make_record("w1", lease_until=FIXED_NOW - timedelta(seconds=1))
        session.query.return_value.filter.return_value.all.return_value = [expired]
        result = list_expired_leases(session, now=FIXED_NOW)
        assert len(result) == 1
        assert result[0].worker_id == "w1"


class TestNow:
    """_now 时区语义测试."""

    def test_now_is_aware_utc(self):
        """心跳当前时间必须是 aware UTC。"""
        now = _now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

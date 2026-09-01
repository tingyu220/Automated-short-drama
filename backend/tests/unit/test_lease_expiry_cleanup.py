"""验证租约超时自动清理机制。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.application.services.queue_cycle import advance_queue, DEFAULT_MAX_ATTEMPTS
from backend.domain.queue.queue_item import QueueItem, QueueState


def _make_item(
    item_id="q1",
    task_id="t1",
    state=QueueState.WAITING_TIME,
    priority=0,
    available_at=None,
    claimed_by=None,
    lease_until=None,
    attempt_count=0,
):
    return QueueItem(
        id=item_id,
        task_id=task_id,
        state=state,
        priority=priority,
        available_at=available_at or datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
        claimed_by=claimed_by,
        lease_until=lease_until,
        attempt_count=attempt_count,
        next_run_at=None,
        failure_code=None,
        retry_safe=False,
    )


class FakeQueueRepo:
    """内存队列仓储，模拟 recover_expired + list_by_state + update + claim_next。"""

    def __init__(self, items: list[QueueItem]):
        self.items = {item.id: item for item in items}
        self.recover_calls = []
        self.update_calls = []

    def recover_expired(self, now, max_attempts):
        self.recover_calls.append((now, max_attempts))
        requeued = []
        manual = []
        for item in list(self.items.values()):
            if item.state in (QueueState.CLAIMED, QueueState.RUNNING):
                if item.lease_until and item.lease_until < now:
                    new_attempt = item.attempt_count + 1
                    if new_attempt <= max_attempts:
                        item.state = QueueState.QUEUED
                        item.claimed_by = None
                        item.lease_until = None
                        item.attempt_count = new_attempt
                        requeued.append(item)
                    else:
                        item.state = QueueState.MANUAL_REVIEW
                        item.claimed_by = None
                        item.lease_until = None
                        manual.append(item)
        return requeued, manual

    def list_by_state(self, state):
        return [item for item in self.items.values() if item.state == state]

    def update(self, item):
        self.items[item.id] = item
        self.update_calls.append(item.id)
        return item

    def claim_next(self, worker_id, lease_seconds, now):
        candidates = [
            item for item in self.items.values()
            if item.state == QueueState.QUEUED
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x.priority, x.available_at, x.id))
        item = candidates[0]
        item.state = QueueState.CLAIMED
        item.claimed_by = worker_id
        item.lease_until = now + timedelta(seconds=lease_seconds)
        return item


class TestLeaseExpiryCleanup:
    """租约超时自动清理。"""

    def test_expired_claimed_recovered_to_queued(self):
        """过期 CLAIMED 项被清理回 QUEUED，attempt_count +1，然后被重新领取。"""
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        expired = _make_item(
            item_id="q1",
            state=QueueState.CLAIMED,
            lease_until=now - timedelta(minutes=10),
            attempt_count=0,
        )
        repo = FakeQueueRepo([expired])

        advance_queue(repo, now, "worker-1", 60)

        assert len(repo.recover_calls) == 1
        # 清理后 attempt_count +1，然后被重新领取为 CLAIMED
        assert expired.attempt_count == 1
        assert expired.claimed_by == "worker-1"
        assert expired.state == QueueState.CLAIMED

    def test_expired_exceeds_max_attempts_to_manual_review(self):
        """超过 max_attempts 的过期项转 MANUAL_REVIEW。"""
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        expired = _make_item(
            item_id="q1",
            state=QueueState.RUNNING,
            lease_until=now - timedelta(minutes=5),
            attempt_count=DEFAULT_MAX_ATTEMPTS,
        )
        repo = FakeQueueRepo([expired])

        advance_queue(repo, now, "worker-1", 60)

        assert expired.state == QueueState.MANUAL_REVIEW
        assert expired.claimed_by is None

    def test_non_expired_claimed_not_touched(self):
        """未过期的 CLAIMED 项不受影响。"""
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        active = _make_item(
            item_id="q1",
            state=QueueState.CLAIMED,
            lease_until=now + timedelta(minutes=10),
            attempt_count=0,
        )
        waiting = _make_item(
            item_id="q2",
            state=QueueState.WAITING_TIME,
            available_at=now - timedelta(minutes=5),
        )
        repo = FakeQueueRepo([active, waiting])

        advance_queue(repo, now, "worker-1", 60)

        assert active.state == QueueState.CLAIMED
        assert active.attempt_count == 0

    def test_waiting_item_still_enqueued(self):
        """清理后仍正常入队 WAITING_TIME 项。"""
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        waiting = _make_item(
            item_id="q2",
            state=QueueState.WAITING_TIME,
            available_at=now - timedelta(minutes=5),
        )
        repo = FakeQueueRepo([waiting])

        enqueued, claimed = advance_queue(repo, now, "worker-1", 60)

        assert len(enqueued) == 1
        assert claimed is not None

    def test_recovered_item_can_be_reclaimed(self):
        """被清理回 QUEUED 的项可以被重新领取。"""
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        expired = _make_item(
            item_id="q1",
            task_id="t1",
            state=QueueState.CLAIMED,
            lease_until=now - timedelta(minutes=10),
            attempt_count=1,
        )
        repo = FakeQueueRepo([expired])

        enqueued, claimed = advance_queue(repo, now, "worker-2", 60)

        assert claimed is not None
        assert claimed.id == "q1"
        assert claimed.claimed_by == "worker-2"
        assert claimed.state == QueueState.CLAIMED

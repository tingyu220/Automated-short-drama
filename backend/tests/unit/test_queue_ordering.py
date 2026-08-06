"""测试队列排序与入队服务."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.application.services.queue_service import (
    enqueue_when_ready,
    peek_next,
    to_claimed,
)


def _make_item(task_id: str, state: str = QueueState.WAITING_TIME,
               priority: int = 0, available_at: datetime | None = None) -> QueueItem:
    """快速构造 QueueItem。"""
    now = datetime.now(timezone.utc)
    item = QueueItem(
        task_id=task_id,
        state=state,
        priority=priority,
        available_at=available_at or now,
    )
    item.id = task_id  # 测试中直接用 task_id 当 id
    return item


class TestEnqueueWhenReady:

    def test_converts_ready_items_to_queued(self) -> None:
        """enqueue_when_ready 只返回匹配项：WAITING_TIME 且 available_at <= now。"""
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=5)
        future = now + timedelta(hours=1)

        items = [
            _make_item("t1", state=QueueState.WAITING_TIME, available_at=past),
            _make_item("t2", state=QueueState.WAITING_TIME, available_at=future),
            _make_item("t3", state=QueueState.QUEUED, available_at=past),
        ]

        result = enqueue_when_ready(items, now)

        # 只返回 t1（到期且 WAITING_TIME）；t2 未到期，t3 已 QUEUED 不匹配
        assert len(result) == 1
        assert result[0].id == "t1"
        assert result[0].state == QueueState.QUEUED

    def test_does_not_return_non_matching(self) -> None:
        """已 QUEUED 的项不在返回结果中（不是 WAITING_TIME）。"""
        now = datetime.now(timezone.utc)
        items = [_make_item("t1", state=QueueState.QUEUED)]
        result = enqueue_when_ready(items, now)
        assert result == []

    def test_returns_deep_copies(self) -> None:
        """返回的是副本，原列表不受影响。"""
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=5)
        items = [_make_item("t1", state=QueueState.WAITING_TIME, available_at=past)]
        result = enqueue_when_ready(items, now)
        assert len(result) == 1
        assert result[0].state == QueueState.QUEUED
        assert items[0].state == QueueState.WAITING_TIME  # 原列表不变

    def test_cross_timezone_naive_stored_time_compared_as_utc(self) -> None:
        """SQLite 回读的 naive UTC 值应与 aware UTC now 正确比较。"""
        shanghai_release = datetime(
            2026, 8, 8, 0, 30, tzinfo=timezone(timedelta(hours=8))
        )
        utc_release = shanghai_release.astimezone(timezone.utc)
        stored_naive = utc_release.replace(tzinfo=None)
        item = _make_item(
            "t1",
            state=QueueState.WAITING_TIME,
            available_at=stored_naive,
        )

        before = enqueue_when_ready(
            [item], now=utc_release - timedelta(minutes=1)
        )
        assert before == []

        at_release = enqueue_when_ready([item], now=utc_release)
        assert [entry.id for entry in at_release] == ["t1"]


class TestPeekNext:

    def test_returns_queued_items_sorted(self) -> None:
        """返回 QUEUED 项，按 priority DESC -> available_at ASC -> id ASC。"""
        now = datetime.now(timezone.utc)
        items = [
            _make_item("t1", state=QueueState.QUEUED, priority=0, available_at=now),
            _make_item("t2", state=QueueState.QUEUED, priority=5, available_at=now + timedelta(minutes=10)),
            _make_item("t3", state=QueueState.QUEUED, priority=5, available_at=now),
            _make_item("t4", state=QueueState.WAITING_TIME, priority=99),  # 非 QUEUED 忽略
        ]
        result = peek_next(items, limit=3)
        assert len(result) == 3
        assert result[0].id == "t3"
        assert result[1].id == "t2"
        assert result[2].id == "t1"

    def test_limit_defaults_to_1(self) -> None:
        """默认 limit=1。"""
        now = datetime.now(timezone.utc)
        items = [
            _make_item("t1", state=QueueState.QUEUED, priority=5, available_at=now),
            _make_item("t2", state=QueueState.QUEUED, priority=3, available_at=now),
        ]
        result = peek_next(items)
        assert len(result) == 1
        assert result[0].id == "t1"

    def test_returns_empty_for_no_queued(self) -> None:
        """没有 QUEUED 项时返回空列表。"""
        items = [_make_item("t1", state=QueueState.WAITING_TIME)]
        assert peek_next(items) == []

    def test_priority_primary_ordering(self) -> None:
        """验证 priority 降序是主排序。"""
        now = datetime.now(timezone.utc)
        items = [
            _make_item("t1", state=QueueState.QUEUED, priority=0, available_at=now),
            _make_item("t2", state=QueueState.QUEUED, priority=10, available_at=now + timedelta(hours=1)),
        ]
        result = peek_next(items, limit=2)
        assert result[0].id == "t2"  # prio 10 > prio 0

    def test_id_tiebreaker(self) -> None:
        """同 priority 同 available_at 时按 id 升序。"""
        now = datetime.now(timezone.utc)
        items = [
            _make_item("b", state=QueueState.QUEUED, priority=0, available_at=now),
            _make_item("a", state=QueueState.QUEUED, priority=0, available_at=now),
        ]
        result = peek_next(items, limit=2)
        assert result[0].id == "a"


class TestToClaimed:

    def test_transitions_to_claimed_and_sets_fields(self) -> None:
        """QUEUED->CLAIMED，写入 claimed_by 和 lease_until。"""
        now = datetime.now(timezone.utc)
        future = now + timedelta(minutes=5)
        item = _make_item("t1", state=QueueState.QUEUED)
        result = to_claimed(item, worker_id="w1", lease_until=future)

        assert result.state == QueueState.CLAIMED
        assert result.claimed_by == "w1"
        assert result.lease_until == future

    def test_original_not_modified(self) -> None:
        """原始 item 不受影响。"""
        now = datetime.now(timezone.utc)
        future = now + timedelta(minutes=5)
        item = _make_item("t1", state=QueueState.QUEUED)
        to_claimed(item, worker_id="w1", lease_until=future)
        assert item.state == QueueState.QUEUED
        assert item.claimed_by is None

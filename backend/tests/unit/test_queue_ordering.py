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
        """WAITING_TIME 且 available_at <= now 的项转为 QUEUED。"""
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=5)
        future = now + timedelta(hours=1)

        items = [
            _make_item("t1", state=QueueState.WAITING_TIME, available_at=past),
            _make_item("t2", state=QueueState.WAITING_TIME, available_at=future),
            _make_item("t3", state=QueueState.QUEUED, available_at=past),
        ]

        result = enqueue_when_ready(items, now)

        assert result[0].state == QueueState.QUEUED   # 到期 → 入队
        assert result[1].state == QueueState.WAITING_TIME  # 未到期
        assert result[2].state == QueueState.QUEUED   # 已是 QUEUED 不动

    def test_does_not_double_enqueue(self) -> None:
        """已 QUEUED 的项不会被重复转换。"""
        now = datetime.now(timezone.utc)
        items = [_make_item("t1", state=QueueState.QUEUED)]
        result = enqueue_when_ready(items, now)
        assert result[0].state == QueueState.QUEUED

    def test_returns_deep_copies(self) -> None:
        """返回的是副本，原列表不受影响。"""
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=5)
        items = [_make_item("t1", state=QueueState.WAITING_TIME, available_at=past)]
        result = enqueue_when_ready(items, now)
        assert result[0].state == QueueState.QUEUED
        assert items[0].state == QueueState.WAITING_TIME  # 原列表不变


class TestPeekNext:

    def test_returns_queued_items_sorted(self) -> None:
        """返回 QUEUED 项，按 priority DESC → available_at ASC → id ASC。"""
        now = datetime.now(timezone.utc)
        items = [
            _make_item("t1", state=QueueState.QUEUED, priority=0, available_at=now),
            _make_item("t2", state=QueueState.QUEUED, priority=5, available_at=now + timedelta(minutes=10)),
            _make_item("t3", state=QueueState.QUEUED, priority=5, available_at=now),
            _make_item("t4", state=QueueState.WAITING_TIME, priority=99),  # 非 QUEUED 忽略
        ]
        # 排序: priority DESC: t2(5)>t3(5)>t1(0); 同 priority: t3(avail early)>t2(avail late)
        # 期望顺序: t3, t2, t1
        # 注意 id 排序: t3 vs t2 按 available_at 排，t3 更早; 如果 available_at 相同则按 id
        result = peek_next(items, limit=3)
        assert len(result) == 3
        # 修正预期: t3(prio5, avail=now) > t2(prio5, avail=now+10min) > t1(prio0)
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
        """QUEUED→CLAIMED，写入 claimed_by 和 lease_until。"""
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

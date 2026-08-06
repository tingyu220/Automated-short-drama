"""recovery_service 单元测试 —— 使用 fake repository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.application.services.recovery_service import (
    RecoveryResult,
    recover_expired,
)
from backend.domain.errors.domain_error import ConflictError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)


class FakeSession:
    """最小 fake session，仅用于传递到 repo."""

    def add(self, obj: object) -> None:
        pass

    def flush(self) -> None:
        pass

    def get(self, model: type, ident: str) -> object | None:
        return None

    def execute(self, stmt: object):
        raise NotImplementedError("FakeSession 不应执行 SQL")


class FakeQueueRepository(SqlAlchemyQueueRepository):
    """覆盖 find_expired / get / update，模拟数据库行为."""

    def __init__(self) -> None:
        super().__init__(FakeSession())
        self._items: dict[str, QueueItem] = {}
        # 由外部设置 find_expired 返回的列表
        self._expired_items: list[QueueItem] = []

    def add(self, item: QueueItem) -> QueueItem:
        self._items[item.id] = item
        return item

    def get(self, item_id: str) -> QueueItem | None:
        return self._items.get(item_id)

    def update(self, item: QueueItem) -> QueueItem:
        if item.id not in self._items:
            raise ValueError(f"QueueItem {item.id} not found")
        self._items[item.id] = item
        return item

    def list_by_state(self, state: str) -> list[QueueItem]:
        return [i for i in self._items.values() if i.state == state]

    def find_expired(self, now: datetime) -> list[QueueItem]:
        """返回预设的过期项列表."""
        return list(self._expired_items)


def make_item(
    item_id: str = "q-1",
    state: str = QueueState.CLAIMED,
    claimed_by: str | None = "worker-1",
    attempt_count: int = 0,
    lease_until: datetime | None = None,
) -> QueueItem:
    return QueueItem(
        id=item_id,
        task_id="task-1",
        state=state,
        claimed_by=claimed_by,
        attempt_count=attempt_count,
        lease_until=lease_until,
    )


@pytest.fixture
def fake_repo() -> FakeQueueRepository:
    return FakeQueueRepository()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 6, 12, 0, 0)


class TestRecoverExpired:
    """recover_expired 核心逻辑测试."""

    def test_expired_claimed_requeued(self, monkeypatch, fake_repo, now):
        """过期 CLAIMED 项：attempt_count+1 → QUEUED，claimed_by/lease_until 清空."""
        item = make_item(
            "q-1",
            state=QueueState.CLAIMED,
            claimed_by="worker-1",
            attempt_count=0,
        )
        item.lease_until = now - timedelta(seconds=1)
        fake_repo._expired_items = [item]
        fake_repo._items["q-1"] = item

        monkeypatch.setattr(
            "backend.application.services.recovery_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        result = recover_expired(FakeSession(), now)

        assert len(result.requeued) == 1
        assert len(result.manual_review) == 0

        updated = fake_repo.get("q-1")
        assert updated.state == QueueState.QUEUED
        assert updated.attempt_count == 1
        assert updated.claimed_by is None
        assert updated.lease_until is None

    def test_expired_exceeds_max_attempts_to_manual_review(
        self, monkeypatch, fake_repo, now
    ):
        """过期项 attempt_count 已达 max_attempts，进入 MANUAL_REVIEW."""
        item = make_item(
            "q-1",
            state=QueueState.RUNNING,
            claimed_by="worker-1",
            attempt_count=3,  # = max_attempts default
        )
        item.lease_until = now - timedelta(seconds=1)
        fake_repo._expired_items = [item]
        fake_repo._items["q-1"] = item

        monkeypatch.setattr(
            "backend.application.services.recovery_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        result = recover_expired(FakeSession(), now)

        assert len(result.requeued) == 0
        assert len(result.manual_review) == 1

        updated = fake_repo.get("q-1")
        assert updated.state == QueueState.MANUAL_REVIEW
        assert updated.attempt_count == 4
        assert updated.claimed_by is None
        assert updated.lease_until is None

    def test_non_expired_not_touched(self, monkeypatch, fake_repo, now):
        """未过期项不应被恢复."""
        # find_expired 返回空列表
        fake_repo._expired_items = []

        monkeypatch.setattr(
            "backend.application.services.recovery_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        result = recover_expired(FakeSession(), now)

        assert len(result.requeued) == 0
        assert len(result.manual_review) == 0

    def test_illegal_transition_raises_conflict(
        self, monkeypatch, fake_repo, now
    ):
        """从非法状态（如 COMPLETED）恢复应抛 ConflictError."""
        item = make_item(
            "q-1",
            state=QueueState.COMPLETED,  # COMPLETED 不能迁移到任何状态
            claimed_by="worker-1",
        )
        item.lease_until = now - timedelta(seconds=1)
        fake_repo._expired_items = [item]
        fake_repo._items["q-1"] = item

        monkeypatch.setattr(
            "backend.application.services.recovery_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        with pytest.raises(ConflictError):
            recover_expired(FakeSession(), now)

    def test_mixed_expired_below_and_above_max(
        self, monkeypatch, fake_repo, now
    ):
        """混合场景：部分 requeue，部分 manual_review."""
        item1 = make_item(
            "q-1", state=QueueState.CLAIMED, attempt_count=0
        )
        item1.lease_until = now - timedelta(seconds=1)
        item2 = make_item(
            "q-2", state=QueueState.RUNNING, attempt_count=3
        )
        item2.lease_until = now - timedelta(seconds=1)

        fake_repo._expired_items = [item1, item2]
        fake_repo._items["q-1"] = item1
        fake_repo._items["q-2"] = item2

        monkeypatch.setattr(
            "backend.application.services.recovery_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        result = recover_expired(FakeSession(), now)

        assert len(result.requeued) == 1
        assert len(result.manual_review) == 1
        assert result.requeued[0].id == "q-1"
        assert result.manual_review[0].id == "q-2"

    def test_custom_max_attempts(self, monkeypatch, fake_repo, now):
        """自定义 max_attempts=5，attempt_count=5 仍触发 REQUeued."""
        item = make_item(
            "q-1", state=QueueState.CLAIMED, attempt_count=4
        )
        item.lease_until = now - timedelta(seconds=1)
        fake_repo._expired_items = [item]
        fake_repo._items["q-1"] = item

        monkeypatch.setattr(
            "backend.application.services.recovery_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        result = recover_expired(FakeSession(), now, max_attempts=5)

        assert len(result.requeued) == 1
        assert len(result.manual_review) == 0

        updated = fake_repo.get("q-1")
        assert updated.state == QueueState.QUEUED
        assert updated.attempt_count == 5

"""claim_service 单元测试 —— 使用 fake repository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.application.services.claim_service import (
    claim_next_task,
    release_claimed,
)
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)


class FakeSession:
    """最小 fake session，仅用于传递到 repo，不真正执行 SQL."""

    def add(self, obj: object) -> None:
        pass

    def flush(self) -> None:
        pass

    def get(self, model: type, ident: str) -> object | None:
        return None

    def execute(self, stmt: object):
        raise NotImplementedError("FakeSession 不应执行 SQL")


class FakeQueueRepository(SqlAlchemyQueueRepository):
    """覆盖 claim_next / get / update，模拟数据库行为."""

    def __init__(self) -> None:
        super().__init__(FakeSession())
        self._items: dict[str, QueueItem] = {}
        self._claim_next_calls: list[tuple] = []

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

    def claim_next(
        self, worker_id: str, lease_seconds: int, now: datetime
    ) -> QueueItem | None:
        self._claim_next_calls.append((worker_id, lease_seconds, now))
        return getattr(self, "_next_item", None)

    def release_claimed(self, item_id: str, worker_id: str) -> bool:
        """模拟条件原子释放。"""
        item = self._items.get(item_id)
        if (
            item is None
            or item.claimed_by != worker_id
            or item.state
            not in (QueueState.CLAIMED, QueueState.RUNNING)
        ):
            return False
        item.state = QueueState.QUEUED
        item.claimed_by = None
        item.lease_until = None
        self._items[item.id] = item
        return True


@pytest.fixture
def fake_repo() -> FakeQueueRepository:
    return FakeQueueRepository()


def make_item(
    item_id: str = "q-1",
    state: str = QueueState.QUEUED,
    claimed_by: str | None = None,
) -> QueueItem:
    return QueueItem(
        id=item_id,
        task_id="task-1",
        state=state,
        claimed_by=claimed_by,
    )


class TestClaimNextTask:

    def test_claim_success_returns_item(self, monkeypatch, fake_repo):
        item = make_item(state=QueueState.CLAIMED, claimed_by="worker-1")
        fake_repo._next_item = item
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )
        result = claim_next_task(FakeSession(), "worker-1", lease_seconds=60)
        assert result is not None
        assert result.state == QueueState.CLAIMED
        assert result.claimed_by == "worker-1"

    def test_claim_passes_aware_utc_now(self, monkeypatch, fake_repo):
        """claim_next_task 必须向仓储传入 aware UTC 的当前时间。"""
        item = make_item(state=QueueState.CLAIMED, claimed_by="worker-1")
        fake_repo._next_item = item
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        claim_next_task(FakeSession(), "worker-1", lease_seconds=60)

        recorded = fake_repo._claim_next_calls[0][2]
        assert recorded.tzinfo is not None
        assert recorded.utcoffset() == timedelta(0)

    def test_claim_accepts_explicit_utc_now(self, monkeypatch, fake_repo):
        """显式传入 now 时应原样按 aware UTC 传给仓储。"""
        fixed = datetime(2026, 8, 7, 16, 30, tzinfo=timezone.utc)
        item = make_item(state=QueueState.CLAIMED, claimed_by="worker-1")
        fake_repo._next_item = item
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )

        claim_next_task(FakeSession(), "worker-1", lease_seconds=60, now=fixed)

        assert fake_repo._claim_next_calls[0][2] == fixed

    def test_claim_no_available_returns_none(self, monkeypatch, fake_repo):
        fake_repo._next_item = None
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )
        result = claim_next_task(FakeSession(), "worker-1")
        assert result is None


class TestReleaseClaimed:

    def test_release_success(self, monkeypatch, fake_repo):
        item = make_item("q-1", state=QueueState.CLAIMED, claimed_by="worker-1")
        fake_repo._items["q-1"] = item
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )
        ok = release_claimed(FakeSession(), "q-1", "worker-1")
        assert ok is True
        updated = fake_repo.get("q-1")
        assert updated.state == QueueState.QUEUED
        assert updated.claimed_by is None
        assert updated.lease_until is None

    def test_release_wrong_worker_raises_conflict(self, monkeypatch, fake_repo):
        item = make_item("q-1", state=QueueState.CLAIMED, claimed_by="worker-A")
        fake_repo._items["q-1"] = item
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )
        with pytest.raises(ConflictError):
            release_claimed(FakeSession(), "q-1", "worker-B")

    def test_release_nonexistent_raises_not_found(self, monkeypatch, fake_repo):
        monkeypatch.setattr(
            "backend.application.services.claim_service.SqlAlchemyQueueRepository",
            lambda session: fake_repo,
        )
        with pytest.raises(NotFoundError):
            release_claimed(FakeSession(), "nonexistent", "worker-1")

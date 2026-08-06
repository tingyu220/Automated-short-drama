"""resource_release_service 单元测试 —— 使用 fake repos/session/browser."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.services.resource_release_service import (
    BrowserSession,
    ResourceReleaseService,
)
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus


class FakeSession:
    """最小 fake session，仅用于传递到 repo 工厂。"""

    def add(self, obj: object) -> None:
        pass

    def flush(self) -> None:
        pass

    def get(self, model: type, ident: str) -> object | None:
        return None

    def execute(self, stmt: object):
        raise NotImplementedError("FakeSession 不应执行 SQL")


class FakeQueueRepository:
    """模拟 QueueRepository。"""

    def __init__(self, items: dict[str, QueueItem] | None = None) -> None:
        self._items = items or {}

    def add(self, item: QueueItem) -> QueueItem:
        self._items[item.id] = item
        return item

    def get(self, item_id: str) -> QueueItem | None:
        return self._items.get(item_id)

    def update(self, item: QueueItem) -> QueueItem:
        self._items[item.id] = item
        return item

    def list_by_state(self, state: str) -> list[QueueItem]:
        return [i for i in self._items.values() if i.state == state]


class FakeTaskRepository:
    """模拟 TaskRepository。"""

    def __init__(self, tasks: dict[str, DramaTask] | None = None) -> None:
        self._tasks = tasks or {}

    def add(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> DramaTask | None:
        return self._tasks.get(task_id)

    def update(self, task: DramaTask) -> DramaTask:
        self._tasks[task.id] = task
        return task

    def list_by_state(self, state: str) -> list[DramaTask]:
        return [t for t in self._tasks.values() if t.status == state]


class FakeLedgerRepository:
    """模拟 LedgerRepository。"""

    def __init__(self) -> None:
        self._ledgers: dict[str, TaskLedger] = {}

    def add(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger


class FakeBrowser(BrowserSession):
    """模拟浏览器会话。"""

    def __init__(self, last_active: datetime) -> None:
        self.last_active = last_active
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _make_item(
    item_id: str = "qi-1",
    state: str = QueueState.CLAIMED,
    claimed_by: str = "worker-1",
) -> QueueItem:
    return QueueItem(id=item_id, task_id="task-1", state=state, claimed_by=claimed_by)


def _make_task(task_id: str = "task-1") -> DramaTask:
    return DramaTask(
        id=task_id,
        drama_name="test-drama",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        status=TaskStatus.RUNNING,
    )


def _patch_repos(
    monkeypatch,
    queue_repo: FakeQueueRepository,
    task_repo: FakeTaskRepository,
    ledger_repo: FakeLedgerRepository,
) -> None:
    """将服务内 repo 工厂替换为 fake。"""
    monkeypatch.setattr(
        "backend.application.services.resource_release_service.SqlAlchemyQueueRepository",
        lambda session: queue_repo,
    )
    monkeypatch.setattr(
        "backend.application.services.resource_release_service.SqlAlchemyTaskRepository",
        lambda session: task_repo,
    )
    monkeypatch.setattr(
        "backend.application.services.resource_release_service.SqlAlchemyLedgerRepository",
        lambda session: ledger_repo,
    )


class TestReleaseAfterCompletion:
    """release_after_completion 单元测试。"""

    def test_completes_releases_lease_and_closes_browser(self, monkeypatch):
        """完成后返回 ledger，租约被释放，浏览器被关闭。"""
        item = _make_item()
        task = _make_task()
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        _patch_repos(monkeypatch, queue_repo, task_repo, ledger_repo)

        browser = FakeBrowser(datetime(2026, 8, 6, 11, 0, tzinfo=timezone.utc))
        released: list[str] = []

        def fake_release(session, worker_id: str) -> bool:
            released.append(worker_id)
            return True

        service = ResourceReleaseService()
        ledger = service.release_after_completion(
            FakeSession(),
            "qi-1",
            "worker-1",
            {"album_id": "alb-123"},
            browser_session=browser,
            release_lease=fake_release,
        )

        assert isinstance(ledger, TaskLedger)
        assert ledger.final_status == "COMPLETED"
        assert ledger.album_id == "alb-123"
        assert released == ["worker-1"]
        assert browser.closed is True
        assert item.state == QueueState.COMPLETED
        assert task.status == TaskStatus.COMPLETED

    def test_uses_default_release_lease(self, monkeypatch):
        """未注入 release_lease 时使用 worker_heartbeat.release_lease。"""
        item = _make_item()
        task = _make_task()
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        _patch_repos(monkeypatch, queue_repo, task_repo, ledger_repo)

        released: list[str] = []

        def fake_release(session, worker_id: str) -> bool:
            released.append(worker_id)
            return True

        monkeypatch.setattr(
            "backend.application.services.worker_heartbeat.release_lease",
            fake_release,
        )

        service = ResourceReleaseService()
        ledger = service.release_after_completion(
            FakeSession(), "qi-1", "worker-1", {}
        )

        assert ledger.final_status == "COMPLETED"
        assert released == ["worker-1"]

    def test_without_browser_skips_close(self, monkeypatch):
        """browser_session 为空时不调用 close。"""
        item = _make_item()
        task = _make_task()
        queue_repo = FakeQueueRepository({"qi-1": item})
        task_repo = FakeTaskRepository({"task-1": task})
        ledger_repo = FakeLedgerRepository()
        _patch_repos(monkeypatch, queue_repo, task_repo, ledger_repo)

        service = ResourceReleaseService()
        ledger = service.release_after_completion(
            FakeSession(),
            "qi-1",
            "worker-1",
            {},
            release_lease=lambda session, worker_id: True,
        )

        assert ledger.final_status == "COMPLETED"


class TestReleaseIdleBrowser:
    """release_idle_browser 单元测试。"""

    def test_expired_closes_and_returns_true(self):
        """last_active + idle_seconds < now 时关闭并返回 True。"""
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        browser = FakeBrowser(now - timedelta(seconds=61))

        service = ResourceReleaseService()
        result = service.release_idle_browser(browser, idle_seconds=60, now=now)

        assert result is True
        assert browser.closed is True

    def test_not_expired_keeps_open_and_returns_false(self):
        """未超时则不关闭并返回 False。"""
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        browser = FakeBrowser(now - timedelta(seconds=59))

        service = ResourceReleaseService()
        result = service.release_idle_browser(browser, idle_seconds=60, now=now)

        assert result is False
        assert browser.closed is False

    def test_boundary_keeps_open(self):
        """恰好等于 idle_seconds 时视为未到期。"""
        now = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        browser = FakeBrowser(now - timedelta(seconds=60))

        service = ResourceReleaseService()
        result = service.release_idle_browser(browser, idle_seconds=60, now=now)

        assert result is False
        assert browser.closed is False

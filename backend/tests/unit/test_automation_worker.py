"""Automation Worker 运行模式装配测试。"""
from __future__ import annotations

from types import SimpleNamespace

from backend.bootstrap import automation_worker
from backend.domain.runtime.environment import RuntimeMode


def test_runtime_settings_override_adapter_mode_without_mutating_base_settings():
    """Worker 必须以持久化运行环境覆盖启动配置，且不污染基础配置。"""
    settings = SimpleNamespace(use_real_adapters=False)

    resolved = automation_worker._settings_for_runtime_mode(
        settings, RuntimeMode.REAL
    )

    assert resolved.use_real_adapters is True
    assert settings.use_real_adapters is False


def test_worker_checks_runtime_mode_with_short_default_poll_interval(monkeypatch):
    """Worker 默认应每秒检查一次运行模式，避免切换被 15 秒心跳间隔拖慢。"""
    captured: list[float] = []

    class FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(automation_worker, "run_migrations", lambda: None)
    monkeypatch.setattr(automation_worker, "_seed_defaults", lambda *args: None)
    monkeypatch.setattr(automation_worker, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        automation_worker,
        "SqlAlchemyWorkerLeaseRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(automation_worker, "_get_host", lambda: "host")
    monkeypatch.setattr(automation_worker, "_get_pid", lambda: 1)
    monkeypatch.setattr(automation_worker, "acquire_lease", lambda *args: True)
    monkeypatch.setattr(automation_worker, "release_lease", lambda *args: None)
    monkeypatch.setattr(
        automation_worker,
        "_sync_worker_runtime",
        lambda *args, **kwargs: (None, None, RuntimeMode.MOCK, kwargs.get("settings")),
    )

    def stop_after_first_sleep(seconds):
        captured.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(automation_worker.time, "sleep", stop_after_first_sleep)

    assert automation_worker.main([]) == 0
    assert captured == [1]


def test_sync_worker_runtime_rebuilds_browser_and_marks_applied_mode(monkeypatch):
    """环境变更必须先重建运行时，再回写 Worker 的已生效模式。"""
    session = SimpleNamespace(commit_count=0)
    session.commit = lambda: setattr(session, "commit_count", session.commit_count + 1)
    events: list[str] = []

    class EnvironmentRepo:
        def __init__(self, _session):
            pass

        def get(self):
            return SimpleNamespace(desired_mode=RuntimeMode.REAL)

        def mark_worker_mode(self, mode):
            events.append(f"marked:{mode}")

    old_browser = SimpleNamespace(close=lambda: events.append("closed"))
    new_browser = object()
    page = object()
    monkeypatch.setattr(
        automation_worker, "SqlAlchemyRuntimeEnvironmentRepository", EnvironmentRepo
    )
    monkeypatch.setattr(
        automation_worker,
        "_start_worker_browser",
        lambda settings: (new_browser, page),
    )

    runtime, actual_page, mode, runtime_settings = automation_worker._sync_worker_runtime(
        session,
        SimpleNamespace(use_real_adapters=False),
        old_browser,
        object(),
        RuntimeMode.MOCK,
    )

    assert runtime is new_browser
    assert actual_page is page
    assert mode == RuntimeMode.REAL
    assert runtime_settings.use_real_adapters is True
    assert events == ["closed", "marked:REAL"]
    assert session.commit_count == 1


def test_sync_worker_runtime_does_not_mark_mode_when_browser_start_fails(monkeypatch):
    """真实浏览器启动失败时，环境必须保持切换中。"""
    session = SimpleNamespace(commit_count=0)
    session.commit = lambda: setattr(session, "commit_count", session.commit_count + 1)
    marked: list[str] = []

    class EnvironmentRepo:
        def __init__(self, _session):
            pass

        def get(self):
            return SimpleNamespace(desired_mode=RuntimeMode.REAL)

        def mark_worker_mode(self, mode):
            marked.append(mode)

    monkeypatch.setattr(
        automation_worker, "SqlAlchemyRuntimeEnvironmentRepository", EnvironmentRepo
    )
    monkeypatch.setattr(
        automation_worker,
        "_start_worker_browser",
        lambda settings: (_ for _ in ()).throw(RuntimeError("browser failed")),
    )

    import pytest

    with pytest.raises(RuntimeError, match="browser failed"):
        automation_worker._sync_worker_runtime(
            session,
            SimpleNamespace(use_real_adapters=False),
            None,
            None,
            RuntimeMode.MOCK,
        )

    assert marked == []
    assert session.commit_count == 0


def test_sync_worker_runtime_rebuilds_dead_browser_without_mode_change(monkeypatch):
    """模式不变但浏览器窗口被关闭时，Worker 也必须重建运行时。"""
    session = SimpleNamespace(commit_count=0)
    session.commit = lambda: setattr(session, "commit_count", session.commit_count + 1)
    events: list[str] = []

    class EnvironmentRepo:
        def __init__(self, _session):
            pass

        def get(self):
            return SimpleNamespace(desired_mode=RuntimeMode.REAL)

        def mark_worker_mode(self, mode):
            events.append(f"marked:{mode}")

    class DeadBrowser:
        def is_alive(self):
            return False

        def close(self):
            events.append("closed")

    new_browser = SimpleNamespace(is_alive=lambda: True)
    new_page = object()
    monkeypatch.setattr(
        automation_worker, "SqlAlchemyRuntimeEnvironmentRepository", EnvironmentRepo
    )
    monkeypatch.setattr(
        automation_worker,
        "_start_worker_browser",
        lambda settings: (new_browser, new_page),
    )

    runtime, page, mode, _ = automation_worker._sync_worker_runtime(
        session,
        SimpleNamespace(use_real_adapters=True),
        DeadBrowser(),
        object(),
        RuntimeMode.REAL,
    )

    assert runtime is new_browser
    assert page is new_page
    assert mode == RuntimeMode.REAL
    assert events == ["closed", "marked:REAL"]
    assert session.commit_count == 1


def test_run_cycle_commits_claim_before_building_external_executor(monkeypatch) -> None:
    """外部执行和独立续租开始前，领取结果必须已对其他事务可见。"""
    class FakeSession:
        def __init__(self) -> None:
            self.commit_count = 0

        def commit(self) -> None:
            self.commit_count += 1

        def rollback(self) -> None:
            raise AssertionError("成功路径不应回滚")

    session = FakeSession()
    claimed = SimpleNamespace(id="queue-1")
    monkeypatch.setattr(
        automation_worker,
        "heartbeat",
        lambda *args: SimpleNamespace(
            lease_until=SimpleNamespace(isoformat=lambda: "lease")
        ),
    )
    monkeypatch.setattr(
        automation_worker,
        "advance_queue",
        lambda *args: ([], claimed),
    )
    for name in (
        "SqlAlchemyWorkerLeaseRepository",
        "SqlAlchemyQueueRepository",
        "SqlAlchemyTaskRepository",
        "SqlAlchemyLedgerRepository",
        "SqlAlchemyExecutionRepository",
    ):
        monkeypatch.setattr(automation_worker, name, lambda _session: object())

    def build_executor(*args, **kwargs):
        assert session.commit_count == 2
        return object()

    monkeypatch.setattr(automation_worker, "_build_cycle_executor", build_executor)

    class ExecutionService:
        def __init__(self, *args) -> None:
            pass

        def process_claimed(self, item, now):
            return SimpleNamespace(
                queue_item_id=item.id,
                final_queue_state="COMPLETED",
                ledger_id=None,
                event_count=0,
            )

    monkeypatch.setattr(automation_worker, "WorkerExecutionService", ExecutionService)

    automation_worker._run_cycle(
        session,
        "worker-1",
        "host",
        1,
        60,
        settings=SimpleNamespace(use_real_adapters=False),
    )

    assert session.commit_count == 3


def test_cycle_executor_uses_real_mode_from_settings(monkeypatch) -> None:
    """生产配置开启时必须把同一个 page 和真实模式传到底层。"""
    settings = SimpleNamespace(use_real_adapters=True)
    page = object()
    session = object()
    bundle = object()
    executor = object()
    captured: dict[str, object] = {}

    def fake_build_adapters(received_settings, *, page=None):
        captured["adapter_settings"] = received_settings
        captured["page"] = page
        return bundle

    def fake_build_link_readiness_executor(
        received_settings,
        received_bundle,
        received_session,
        *,
        use_real_adapters=False,
        on_poll_wait=None,
        page=None,
    ):
        captured["executor_settings"] = received_settings
        captured["bundle"] = received_bundle
        captured["session"] = received_session
        captured["use_real_adapters"] = use_real_adapters
        captured["on_poll_wait"] = on_poll_wait
        captured["executor_page"] = page
        return executor

    monkeypatch.setattr(automation_worker, "build_adapters", fake_build_adapters)
    monkeypatch.setattr(
        automation_worker,
        "build_link_readiness_executor",
        fake_build_link_readiness_executor,
    )

    result = automation_worker._build_cycle_executor(
        session,
        settings,
        page=page,
        use_mock_executor=False,
    )

    assert result is executor
    assert captured == {
        "adapter_settings": settings,
        "page": page,
        "executor_settings": settings,
        "bundle": bundle,
        "session": session,
        "use_real_adapters": True,
        "on_poll_wait": None,
        "executor_page": page,
    }


def test_cycle_executor_uses_dry_run_when_runtime_is_mock(monkeypatch) -> None:
    """模拟环境不得生成链接就绪或投放系统已搭建结果。"""
    expected = object()
    monkeypatch.setattr(automation_worker, "mock_worker_executor", lambda: expected)
    monkeypatch.setattr(
        automation_worker,
        "build_adapters",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("模拟环境不应装配链接就绪执行器")
        ),
    )

    result = automation_worker._build_cycle_executor(
        object(),
        SimpleNamespace(use_real_adapters=False),
    )

    assert result is expected


def test_cycle_executor_can_explicitly_use_legacy_mock(monkeypatch) -> None:
    expected = object()
    monkeypatch.setattr(automation_worker, "mock_worker_executor", lambda: expected)

    result = automation_worker._build_cycle_executor(
        object(),
        SimpleNamespace(use_real_adapters=True),
        page=object(),
        use_mock_executor=True,
    )

    assert result is expected


def test_start_worker_browser_only_in_real_mode(monkeypatch) -> None:
    page = object()
    created: list[object] = []

    class Runtime:
        def __init__(self, sessions_dir):
            created.append(sessions_dir)

        def start(self):
            return page

    monkeypatch.setattr(automation_worker, "WorkerBrowserSession", Runtime)
    real_settings = SimpleNamespace(
        use_real_adapters=True,
        data_dir="data-root",
    )
    mock_settings = SimpleNamespace(
        use_real_adapters=False,
        data_dir="data-root",
    )

    runtime, actual_page = automation_worker._start_worker_browser(real_settings)
    mock_runtime, mock_page = automation_worker._start_worker_browser(mock_settings)

    assert isinstance(runtime, Runtime)
    assert actual_page is page
    assert mock_runtime is None
    assert mock_page is None
    assert len(created) == 1

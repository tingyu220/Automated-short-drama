"""Automation Worker 启动入口.

用法:
    python -m backend.bootstrap.automation_worker [--worker-id ID] [--interval N] [--mode-check-interval N] [--lease-seconds N] [--once] [--skip-seed] [--skip-execution]
"""
from __future__ import annotations

import argparse
from copy import copy
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

from sqlalchemy.orm import Session

from backend.application.services.queue_cycle import advance_queue
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.worker_heartbeat import (
    acquire_lease,
    heartbeat,
    release_lease,
    renew_execution_lease,
)
from backend.application.services.worker_execution import (
    WorkerExecutionService,
    mock_worker_executor,
)
from backend.application.services.worker_executor import build_link_readiness_executor
from backend.bootstrap.adapters import build_adapters
from backend.domain.runtime.environment import RuntimeMode
from backend.infrastructure.config.settings import Settings
from backend.infrastructure.browser.worker_browser import (
    WorkerBrowserSession,
    cleanup_zombie_browsers,
)
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.repositories.execution_repository import (
    SqlAlchemyExecutionRepository,
)
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.repositories.runtime_environment_repository import (
    SqlAlchemyRuntimeEnvironmentRepository,
)
from backend.infrastructure.database.repositories.worker_lease_repository import (
    SqlAlchemyWorkerLeaseRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.models.worker import (  # noqa: F401
    WorkerLeaseRecord,
)


def _get_host() -> str:
    """获取主机名."""
    return socket.gethostname()


def _get_pid() -> int:
    """获取当前进程 PID."""
    return os.getpid()


def _settings_for_runtime_mode(settings: Settings, mode: str) -> Settings:
    """为本轮执行创建独立配置，避免污染 Worker 启动配置。"""
    resolved = copy(settings)
    resolved.use_real_adapters = mode == "REAL"
    return resolved


def _seed_defaults(session: Session, defaults_path: Path | None) -> None:
    """导入默认规则配置；重复导入幂等跳过。"""
    path = defaults_path or (Settings().config_defaults_dir / "rules.json")
    result = seed_rules_from_defaults(session, path)
    session.commit()
    print(
        f"Worker: 默认规则初始化完成 "
        f"(created={result.created_rules}, skipped={result.skipped_rules})"
    )


def _run_cycle(
    session: Session,
    worker_id: str,
    host: str,
    pid: int,
    lease_seconds: int,
    skip_execution: bool = False,
    use_mock_executor: bool = False,
    settings: Settings | None = None,
    page=None,
    browser_runtime=None,
) -> tuple[str, object, object]:
    """执行一轮 Worker cycle：心跳 + 队列推进 + 认领任务执行。

    Returns:
        (summary_text, new_browser_runtime_or_None, new_page_or_None)
        若浏览器在本轮被重建则返回新对象，否则返回 None。
    """
    lease_repo = SqlAlchemyWorkerLeaseRepository(session)
    lease = heartbeat(lease_repo, worker_id, host, pid, lease_seconds)
    heartbeat_text = f"心跳 (lease_until={lease.lease_until.isoformat()})"
    # 心跳先独立提交，避免执行段异常回滚时把租约一并回滚
    session.commit()
    if skip_execution:
        return f"{heartbeat_text}，跳过执行（--skip-execution）", None, None

    now = datetime.now(timezone.utc)
    try:
        queue_repo = SqlAlchemyQueueRepository(session)
        enqueued, claimed = advance_queue(
            queue_repo, now, worker_id, lease_seconds
        )
        if claimed is None:
            session.commit()
            return f"{heartbeat_text}，入队 {len(enqueued)}，无领取任务", None, None

        # 外部执行和续租使用独立事务；先提交领取，保证其能看到所有权与租约。
        session.commit()

        # 领取到任务后再次检查浏览器存活——若已崩溃则立即重建，避免任务失败
        new_runtime, new_page = None, None
        runtime_settings = settings or Settings()
        if (
            runtime_settings.use_real_adapters
            and browser_runtime is not None
            and not _is_worker_browser_alive(browser_runtime)
        ):
            print(f"Worker {worker_id}: 浏览器已崩溃，执行前重建...")
            browser_runtime.close()
            new_runtime, new_page = _start_worker_browser(runtime_settings)
            page = new_page
        elif (
            runtime_settings.use_real_adapters
            and browser_runtime is not None
            and browser_runtime.storage_changed_on_disk()
        ):
            print(f"Worker {worker_id}: 检测到登录态更新，刷新浏览器上下文...")
            browser_runtime.close()
            new_runtime, new_page = _start_worker_browser(runtime_settings)
            page = new_page

        task_repo = SqlAlchemyTaskRepository(session)
        ledger_repo = SqlAlchemyLedgerRepository(session)
        event_repo = SqlAlchemyExecutionRepository(session)
        runtime_settings = settings or Settings()
        executor = _build_cycle_executor(
            session,
            runtime_settings,
            page=page,
            use_mock_executor=use_mock_executor,
            on_poll_wait=_execution_lease_renewer(
                claimed.id,
                worker_id,
                host,
                pid,
                lease_seconds,
            ),
        )
        service = WorkerExecutionService(
            executor,
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            worker_id,
        )
        result = service.process_claimed(claimed, now)
        session.commit()
        summary = (
            f"{heartbeat_text}，入队 {len(enqueued)}，领取 {result.queue_item_id}，"
            f"最终状态 {result.final_queue_state}，台账 {result.ledger_id or '-'}，"
            f"事件 {result.event_count}"
        )
        return summary, new_runtime, new_page
    except Exception as exc:
        session.rollback()
        return f"{heartbeat_text}，cycle 异常已回滚: {exc}", None, None


def _build_cycle_executor(
    session: Session,
    settings: Settings,
    *,
    page=None,
    use_mock_executor: bool = False,
    on_poll_wait=None,
):
    """按显式运行模式装配执行器，真实模式缺 page 时直接失败。"""
    if use_mock_executor or not settings.use_real_adapters:
        return mock_worker_executor()
    bundle = build_adapters(settings, page=page)
    return build_link_readiness_executor(
        settings,
        bundle,
        session,
        use_real_adapters=settings.use_real_adapters,
        on_poll_wait=on_poll_wait,
    )


def _execution_lease_renewer(
    queue_item_id: str,
    worker_id: str,
    host: str,
    pid: int,
    lease_seconds: int,
):
    """返回使用独立短事务续租的轮询回调。"""
    def renew() -> None:
        heartbeat_session = SessionLocal()
        try:
            renewed = renew_execution_lease(
                SqlAlchemyWorkerLeaseRepository(heartbeat_session),
                SqlAlchemyQueueRepository(heartbeat_session),
                queue_item_id,
                worker_id,
                host,
                pid,
                lease_seconds,
            )
            if not renewed:
                raise RuntimeError("执行租约续期失败，任务可能已失去所有权")
            heartbeat_session.commit()
        except Exception:
            heartbeat_session.rollback()
            raise
        finally:
            heartbeat_session.close()

    return renew


def _start_worker_browser(settings: Settings):
    """真实模式启动单浏览器页面；Mock 模式不创建浏览器。"""
    if not settings.use_real_adapters:
        return None, None
    runtime = WorkerBrowserSession(Path(settings.data_dir) / "sessions")
    return runtime, runtime.start()


def _sync_worker_runtime(
    session: Session,
    settings: Settings,
    browser_runtime,
    page,
    active_mode: str | None,
):
    """在任务领取前应用目标环境，并在浏览器成功重建后确认生效。"""
    environment_repo = SqlAlchemyRuntimeEnvironmentRepository(session)
    target_mode = environment_repo.get().desired_mode
    browser_alive = _is_worker_browser_alive(browser_runtime)
    if active_mode == target_mode and (target_mode != RuntimeMode.REAL or browser_alive):
        return (
            browser_runtime,
            page,
            active_mode,
            _settings_for_runtime_mode(settings, target_mode),
        )

    if browser_runtime is not None:
        browser_runtime.close()

    runtime_settings = _settings_for_runtime_mode(settings, target_mode)
    next_browser_runtime, next_page = _start_worker_browser(runtime_settings)
    environment_repo.mark_worker_mode(target_mode)
    session.commit()
    return next_browser_runtime, next_page, target_mode, runtime_settings


def _is_worker_browser_alive(browser_runtime) -> bool:
    """兼容旧运行时对象，判断真实浏览器是否仍存活。"""
    if browser_runtime is None:
        return False
    checker = getattr(browser_runtime, "is_alive", None)
    if not callable(checker):
        return True
    try:
        return bool(checker())
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数，启动 Worker 心跳循环.

    Returns:
        退出码（0 成功，非 0 失败）.
    """
    parser = argparse.ArgumentParser(
        description="短剧投放全流程自动化工作台 - Automation Worker",
    )
    parser.add_argument(
        "--worker-id",
        default="worker-local-1",
        help="Worker 标识（默认 worker-local-1）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="心跳间隔（秒，默认 15）",
    )
    parser.add_argument(
        "--mode-check-interval",
        type=int,
        default=1,
        help="运行模式检查间隔（秒，默认 1）",
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=60,
        help="租约时长（秒，默认 60）",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        default=False,
        help="跳过数据库迁移",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="单次完整 cycle（心跳+推进+执行）后退出",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        default=False,
        help="跳过默认规则初始化导入",
    )
    parser.add_argument(
        "--skip-execution",
        action="store_true",
        default=False,
        help="跳过任务执行循环，仅保持心跳",
    )
    parser.add_argument(
        "--mock-executor",
        action="store_true",
        default=False,
        help="回退到旧 Mock executor（默认使用真实编排 executor）",
    )
    parser.add_argument(
        "--defaults-path",
        type=Path,
        default=None,
        help="默认规则 JSON 路径（默认 configs/defaults/rules.json）",
    )
    args = parser.parse_args(argv)

    worker_id = args.worker_id
    host = _get_host()
    pid = _get_pid()
    interval = max(args.interval, 1)
    mode_check_interval = min(max(args.mode_check_interval, 1), interval)
    lease_seconds = args.lease_seconds
    settings = Settings()

    # 每执行 N 个任务主动重启浏览器，防止内存泄漏累积导致崩溃
    BROWSER_RESTART_TASK_COUNT = 20

    # 启动前自动执行数据库迁移
    if not args.skip_migrations:
        run_migrations()

    session = SessionLocal()
    lease_repo = SqlAlchemyWorkerLeaseRepository(session)
    browser_runtime = None
    page = None
    active_mode = None
    runtime_settings = settings
    try:
        if not args.skip_seed:
            _seed_defaults(session, args.defaults_path)

        if not acquire_lease(lease_repo, worker_id, host, pid, lease_seconds):
            print(f"Worker {worker_id}: 租约已被其他 Worker 占用，退出.")
            return 1

        print(
            f"Worker {worker_id}: 租约获取成功 "
            f"(host={host}, pid={pid}, lease={lease_seconds}s, interval={interval}s, "
            f"mode_check_interval={mode_check_interval}s)"
        )

        # 启动时清理残留的 Playwright 浏览器僵尸进程
        if not args.skip_execution:
            killed = cleanup_zombie_browsers()
            if killed:
                print(f"Worker {worker_id}: 清理了 {killed} 个残留浏览器进程")

        if not args.skip_execution:
            browser_runtime, page, active_mode, runtime_settings = _sync_worker_runtime(
                session,
                settings,
                browser_runtime,
                page,
                active_mode,
            )

        if args.once:
            summary, _, _ = _run_cycle(
                session,
                worker_id,
                host,
                pid,
                lease_seconds,
                skip_execution=args.skip_execution,
                use_mock_executor=args.mock_executor,
                settings=runtime_settings,
                page=page,
                browser_runtime=browser_runtime,
            )
            print(f"Worker {worker_id}: {summary}")
            return 0

        elapsed_since_cycle = 0
        tasks_since_restart = 0
        while True:
            try:
                time.sleep(mode_check_interval)
                if not args.skip_execution:
                    browser_runtime, page, active_mode, runtime_settings = _sync_worker_runtime(
                        session,
                        settings,
                        browser_runtime,
                        page,
                        active_mode,
                    )
                elapsed_since_cycle += mode_check_interval
                if elapsed_since_cycle < interval:
                    continue
                elapsed_since_cycle = 0
                summary, rebuilt_runtime, rebuilt_page = _run_cycle(
                    session,
                    worker_id,
                    host,
                    pid,
                    lease_seconds,
                    skip_execution=args.skip_execution,
                    use_mock_executor=args.mock_executor,
                    settings=runtime_settings,
                    page=page,
                    browser_runtime=browser_runtime,
                )
                # 若执行前检测到浏览器崩溃并完成重建，更新引用
                if rebuilt_runtime is not None:
                    browser_runtime = rebuilt_runtime
                    page = rebuilt_page
                    tasks_since_restart = 0
                # 每 N 个任务主动重启浏览器，防止内存泄漏累积
                if (
                    not args.skip_execution
                    and runtime_settings.use_real_adapters
                    and browser_runtime is not None
                ):
                    tasks_since_restart += 1
                    if tasks_since_restart >= BROWSER_RESTART_TASK_COUNT:
                        print(
                            f"Worker {worker_id}: 已执行 {tasks_since_restart} 个任务，"
                            f"主动重启浏览器释放内存..."
                        )
                        browser_runtime.close()
                        browser_runtime, page = _start_worker_browser(runtime_settings)
                        tasks_since_restart = 0
                print(f"Worker {worker_id}: {summary}")
            except KeyboardInterrupt:
                print(f"\nWorker {worker_id}: 收到中断信号，释放租约...")
                break
            except Exception:
                print(f"Worker {worker_id}: 心跳异常，释放租约退出.")
                raise
    except KeyboardInterrupt:
        print(f"\nWorker {worker_id}: 收到中断信号（启动阶段），释放租约...")
    except Exception:
        raise
    finally:
        release_lease(lease_repo, worker_id)
        if browser_runtime is not None:
            browser_runtime.close()
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

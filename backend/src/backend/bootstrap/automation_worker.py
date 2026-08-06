"""Automation Worker 启动入口.

用法:
    python -m backend.bootstrap.automation_worker [--worker-id ID] [--interval N] [--lease-seconds N] [--once] [--skip-seed] [--skip-execution]
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.application.services.queue_cycle import advance_queue
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.worker_heartbeat import (
    acquire_lease,
    heartbeat,
    release_lease,
)
from backend.application.services.worker_execution import (
    WorkerExecutionService,
    mock_worker_executor,
)
from backend.infrastructure.config.settings import Settings
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
) -> str:
    """执行一轮 Worker cycle：心跳 + 队列推进 + 认领任务执行。"""
    lease = heartbeat(session, worker_id, host, pid, lease_seconds)
    heartbeat_text = f"心跳 (lease_until={lease.lease_until.isoformat()})"
    if skip_execution:
        session.commit()
        return f"{heartbeat_text}，跳过执行（--skip-execution）"

    now = datetime.now(timezone.utc)
    try:
        queue_repo = SqlAlchemyQueueRepository(session)
        enqueued, claimed = advance_queue(
            session, queue_repo, now, worker_id, lease_seconds
        )
        if claimed is None:
            session.commit()
            return f"{heartbeat_text}，入队 {len(enqueued)}，无领取任务"

        task_repo = SqlAlchemyTaskRepository(session)
        ledger_repo = SqlAlchemyLedgerRepository(session)
        event_repo = SqlAlchemyExecutionRepository(session)
        service = WorkerExecutionService(
            mock_worker_executor(),
            queue_repo,
            task_repo,
            ledger_repo,
            event_repo,
            worker_id,
        )
        result = service.process_claimed(claimed, now)
        session.commit()
        return (
            f"{heartbeat_text}，入队 {len(enqueued)}，领取 {result.queue_item_id}，"
            f"最终状态 {result.final_queue_state}，台账 {result.ledger_id or '-'}，"
            f"事件 {result.event_count}"
        )
    except Exception as exc:
        session.rollback()
        return f"{heartbeat_text}，cycle 异常已回滚: {exc}"


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
        help="单次心跳后退出",
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
        "--defaults-path",
        type=Path,
        default=None,
        help="默认规则 JSON 路径（默认 configs/defaults/rules.json）",
    )
    args = parser.parse_args(argv)

    worker_id = args.worker_id
    host = _get_host()
    pid = _get_pid()
    interval = args.interval
    lease_seconds = args.lease_seconds

    # 启动前自动执行数据库迁移
    if not args.skip_migrations:
        run_migrations()

    session = SessionLocal()
    try:
        if not args.skip_seed:
            _seed_defaults(session, args.defaults_path)

        if not acquire_lease(session, worker_id, host, pid, lease_seconds):
            print(f"Worker {worker_id}: 租约已被其他 Worker 占用，退出.")
            return 1

        print(
            f"Worker {worker_id}: 租约获取成功 "
            f"(host={host}, pid={pid}, lease={lease_seconds}s, interval={interval}s)"
        )

        if args.once:
            summary = _run_cycle(
                session,
                worker_id,
                host,
                pid,
                lease_seconds,
                skip_execution=args.skip_execution,
            )
            print(f"Worker {worker_id}: {summary}")
            return 0

        while True:
            try:
                time.sleep(interval)
                summary = _run_cycle(
                    session,
                    worker_id,
                    host,
                    pid,
                    lease_seconds,
                    skip_execution=args.skip_execution,
                )
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
        release_lease(session, worker_id)
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

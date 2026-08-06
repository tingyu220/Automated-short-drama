"""Automation Worker 启动入口.

用法:
    python -m backend.bootstrap.automation_worker [--worker-id ID] [--interval N] [--lease-seconds N] [--once] [--skip-seed]
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import time
from pathlib import Path

from sqlalchemy.orm import Session

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.worker_heartbeat import (
    acquire_lease,
    heartbeat,
    release_lease,
)
from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.engine import create_app_engine
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
            print("单次心跳完成，退出.")
            return 0

        while True:
            try:
                time.sleep(interval)
                lease = heartbeat(session, worker_id, host, pid, lease_seconds)
                print(
                    f"Worker {worker_id}: 心跳 "
                    f"(lease_until={lease.lease_until.isoformat()})"
                )
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

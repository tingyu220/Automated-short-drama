"""资源释放服务 —— 完成后释放 Worker 租约与浏览器会话."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from backend.application.services import worker_heartbeat
from backend.application.services.completion_service import complete_task
from backend.domain.common.timezones import as_utc
from backend.domain.ledger.task_ledger import TaskLedger
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)


class BrowserSession(Protocol):
    """浏览器会话协议，仅暴露空闲判定与关闭能力。"""

    last_active: datetime

    def close(self) -> None: ...


class ResourceReleaseService:
    """任务完成与空闲资源释放编排服务。"""

    def release_after_completion(
        self,
        session: Session,
        queue_item_id: str,
        worker_id: str,
        ledger_fields: dict | None,
        browser_session: BrowserSession | None = None,
        release_lease: Callable[[Session, str], bool] | None = None,
    ) -> TaskLedger:
        """完成出队后释放 Worker 租约与浏览器会话。

        Args:
            session: 数据库会话，由调用方管理事务边界。
            queue_item_id: 队列项 ID。
            worker_id: 完成该任务的 worker。
            ledger_fields: 台账补充字段。
            browser_session: 可选浏览器会话，非空时关闭。
            release_lease: 租约释放函数，默认 worker_heartbeat.release_lease。

        Returns:
            生成的任务台账。
        """
        queue_repo = SqlAlchemyQueueRepository(session)
        task_repo = SqlAlchemyTaskRepository(session)
        ledger_repo = SqlAlchemyLedgerRepository(session)
        ledger = complete_task(
            queue_item_id,
            worker_id,
            queue_repo,
            task_repo,
            ledger_repo,
            ledger_fields,
        )

        if release_lease is None:
            release_lease = worker_heartbeat.release_lease
        release_lease(session, worker_id)

        if browser_session is not None:
            browser_session.close()
        return ledger

    def release_idle_browser(
        self,
        browser_session: BrowserSession,
        idle_seconds: int,
        now: datetime,
    ) -> bool:
        """空闲超时则关闭浏览器并返回 True，否则返回 False。"""
        if (
            as_utc(browser_session.last_active) + timedelta(seconds=idle_seconds)
            < as_utc(now)
        ):
            browser_session.close()
            return True
        return False

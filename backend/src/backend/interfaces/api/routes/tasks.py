"""任务 API 路由：列表、详情、手动入队。"""
from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date as date_type
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import QueueItemView, TaskDetail, TaskSummary

router = APIRouter(tags=["tasks"])

_TERMINAL_STATES = frozenset({QueueState.COMPLETED, QueueState.CANCELLED})


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


def _to_summary(task: DramaTask, item: QueueItem | None) -> TaskSummary:
    """构建任务摘要。"""
    return TaskSummary(
        id=task.id,
        drama_name=task.drama_name,
        platform=task.platform,
        available_time=task.available_time,
        status=task.status,
        owner=task.owner,
        queue_state=item.state if item else None,
        updated_at=task.updated_at,
    )


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(
    date: date_type | None = Query(default=None, description="YYYY-MM-DD"),
    platform: str | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    """按日期/平台/状态/剧名筛选任务，按 available_time 降序。"""
    available_from = None
    available_to = None
    if date is not None:
        available_from = datetime.combine(date, time.min)
        available_to = available_from + timedelta(days=1)

    tasks = SqlAlchemyTaskRepository(db).list_by_filters(
        platform=platform,
        status=status,
        q=q,
        available_from=available_from,
        available_to=available_to,
    )
    latest_by_task: dict[str, QueueItem] = {}
    for item in SqlAlchemyQueueRepository(db).list_all():
        if item.task_id not in latest_by_task:
            latest_by_task[item.task_id] = item
    return [
        _to_summary(task, latest_by_task.get(task.id)) for task in tasks
    ]


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)):
    """返回任务详情，不存在时抛 404。"""
    task = SqlAlchemyTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError(f"DramaTask {task_id} not found")

    queue_items = SqlAlchemyQueueRepository(db).list_by_task(task_id)
    item = queue_items[0] if queue_items else None
    ledgers = SqlAlchemyLedgerRepository(db).list_by_task(task_id)

    summary = _to_summary(task, item)
    return TaskDetail(
        **summary.model_dump(),
        queue_item_id=item.id if item else None,
        attempt_count=item.attempt_count if item else None,
        claimed_by=item.claimed_by if item else None,
        lease_until=item.lease_until if item else None,
        ledger_id=ledgers[0].id if ledgers else None,
    )


@router.post("/tasks/{task_id}/enqueue", response_model=QueueItemView)
def enqueue_task(
    task_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """创建或复用队列项；已存在活动项时返回 409。"""
    task = SqlAlchemyTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError(f"DramaTask {task_id} not found")

    queue_repo = SqlAlchemyQueueRepository(db)
    items = queue_repo.list_by_task(task_id)
    if items:
        item = items[0]
        if item.state not in _TERMINAL_STATES:
            raise ConflictError(
                f"任务 {task_id} 已存在活动队列项 {item.id}（{item.state}）"
            )
        item.state = QueueState.WAITING_TIME
        item.available_at = task.available_time
        item.claimed_by = None
        item.lease_until = None
        item.attempt_count = 0
        item.next_run_at = None
        queue_repo.update(item)
    else:
        item = queue_repo.add(
            QueueItem(
                id=str(uuid.uuid4()),
                task_id=task.id,
                state=QueueState.WAITING_TIME,
                available_at=task.available_time,
            )
        )
        response.status_code = 201

    return QueueItemView.model_validate(item)

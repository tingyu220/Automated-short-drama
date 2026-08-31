"""队列 API 路由：列表与暂停/恢复/取消/重试控制。"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.application.services import task_control_service
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import QueueItemView

router = APIRouter(tags=["queue"])

_TERMINAL_STATES = frozenset({"COMPLETED", "CANCELLED", "DRY_RUN"})


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


class WorkerActionBody(BaseModel):
    """队列控制请求体，worker_id 必填（也可走 query）。"""

    worker_id: str | None = None


def _resolve_worker_id(
    query_worker_id: str | None, body: WorkerActionBody | None
) -> str:
    """从 query 或 body 读取 worker_id，两者均缺失时返回 422。"""
    worker_id = body.worker_id if body else None
    worker_id = worker_id or query_worker_id
    if not worker_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "worker_id 必填（query 或 body）",
            },
        )
    return worker_id


def _repos(db: Session) -> tuple[SqlAlchemyQueueRepository, SqlAlchemyTaskRepository]:
    """创建队列与任务仓储。"""
    return SqlAlchemyQueueRepository(db), SqlAlchemyTaskRepository(db)


@router.get("/queue", response_model=list[QueueItemView])
def list_queue(
    state: str | None = Query(default=None),
    include_terminal: bool = Query(
        default=False, description="是否包含已完成/已取消的终态项"
    ),
    db: Session = Depends(get_db),
):
    """列出队列项，可按 state 过滤。"""
    queue_repo = SqlAlchemyQueueRepository(db)
    if state:
        items = queue_repo.list_by_state(state)
    else:
        items = queue_repo.list_all()
        if not include_terminal:
            items = [
                item for item in items if item.state not in _TERMINAL_STATES
            ]
    items.sort(key=lambda item: (-item.priority, item.available_at, item.id))
    return [QueueItemView.model_validate(item) for item in items]


@router.post("/queue/{queue_item_id}/pause", response_model=QueueItemView)
def pause_queue_item(
    queue_item_id: str,
    worker_id: str | None = Query(default=None),
    body: WorkerActionBody | None = Body(default=None),
    db: Session = Depends(get_db),
):
    """暂停队列项。"""
    queue_repo, task_repo = _repos(db)
    item = task_control_service.pause_task(
        queue_repo,
        task_repo,
        queue_item_id,
        _resolve_worker_id(worker_id, body),
    )
    return QueueItemView.model_validate(item)


@router.post("/queue/{queue_item_id}/resume", response_model=QueueItemView)
def resume_queue_item(
    queue_item_id: str,
    worker_id: str | None = Query(default=None),
    body: WorkerActionBody | None = Body(default=None),
    db: Session = Depends(get_db),
):
    """恢复队列项。"""
    queue_repo, task_repo = _repos(db)
    _resolve_worker_id(worker_id, body)
    item = task_control_service.resume_task(queue_repo, task_repo, queue_item_id)
    return QueueItemView.model_validate(item)


@router.post("/queue/{queue_item_id}/cancel", response_model=QueueItemView)
def cancel_queue_item(
    queue_item_id: str,
    worker_id: str | None = Query(default=None),
    body: WorkerActionBody | None = Body(default=None),
    db: Session = Depends(get_db),
):
    """取消队列项。"""
    queue_repo, task_repo = _repos(db)
    item = task_control_service.cancel_task(
        queue_repo,
        task_repo,
        queue_item_id,
        _resolve_worker_id(worker_id, body),
    )
    return QueueItemView.model_validate(item)


@router.post("/queue/{queue_item_id}/retry", response_model=QueueItemView)
def retry_queue_item(
    queue_item_id: str,
    worker_id: str | None = Query(default=None),
    body: WorkerActionBody | None = Body(default=None),
    db: Session = Depends(get_db),
):
    """重试队列项。"""
    queue_repo, task_repo = _repos(db)
    _resolve_worker_id(worker_id, body)
    item = task_control_service.retry_task(queue_repo, task_repo, queue_item_id)
    return QueueItemView.model_validate(item)

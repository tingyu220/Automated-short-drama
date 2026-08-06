"""异常 API 路由：合并 ERROR 事件与 MANUAL_REVIEW 任务。"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.domain.execution.execution_event import EventLevel
from backend.domain.tasks.drama_task import TaskStatus
from backend.infrastructure.database.repositories.execution_repository import (
    SqlAlchemyExecutionRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import ExceptionView

router = APIRouter(tags=["exceptions"])

_MANUAL_REVIEW_MESSAGE = "任务进入人工复核"


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


@router.get("/exceptions", response_model=list[ExceptionView])
def list_exceptions(db: Session = Depends(get_db)):
    """合并 ERROR 执行事件与 MANUAL_REVIEW 任务，按时间降序。"""
    exec_repo = SqlAlchemyExecutionRepository(db)
    task_repo = SqlAlchemyTaskRepository(db)

    items: list[ExceptionView] = [
        ExceptionView(
            id=event.id,
            task_id=event.task_id,
            level=event.level,
            message=event.message,
            occurred_at=event.occurred_at,
        )
        for event in exec_repo.list_events(level=EventLevel.ERROR)
    ]
    items.extend(
        ExceptionView(
            id=task.id,
            task_id=task.id,
            level=TaskStatus.MANUAL_REVIEW,
            message=_MANUAL_REVIEW_MESSAGE,
            occurred_at=task.updated_at,
        )
        for task in task_repo.list_by_state(TaskStatus.MANUAL_REVIEW)
    )
    items.sort(key=lambda item: (item.occurred_at, item.id), reverse=True)
    return items

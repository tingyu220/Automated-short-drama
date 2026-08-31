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
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.repositories.workflow_repository import (
    SqlAlchemyWorkflowRepository,
)
from backend.domain.workflow.step_run import StepStatus
from backend.infrastructure.database.session import get_session
from backend.interfaces.api.schemas import ExceptionView

router = APIRouter(tags=["exceptions"])

_MANUAL_REVIEW_MESSAGE = "任务进入人工复核"
_EVENT_STEP_MAP = {
    "LINK_EXTRACTION": "链接提取",
    "DELIVERY_DRAMA": "搭建投放剧目",
    "PROMOTION_CONFIG": "搭建推广内容",
    "ACCOUNT_ALLOCATION": "账户分配",
    "DELIVERY": "标准投放",
    "TASK_STARTED": "任务开始",
    "TASK_COMPLETED": "任务完成",
    "STEP_FAILED": "步骤执行",
    "PLANSPEC": "PlanSpec",
}
_RESOLVED_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.CANCELLED,
    TaskStatus.DRY_RUN,
    TaskStatus.LINK_EXTRACTED,
    TaskStatus.LINK_READY,
}


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


@router.get("/exceptions", response_model=list[ExceptionView])
def list_exceptions(db: Session = Depends(get_db)):
    """合并 ERROR 执行事件与 MANUAL_REVIEW 任务，按时间降序。"""
    exec_repo = SqlAlchemyExecutionRepository(db)
    task_repo = SqlAlchemyTaskRepository(db)
    queue_repo = SqlAlchemyQueueRepository(db)
    workflow_repo = SqlAlchemyWorkflowRepository(db)
    manual_review_tasks = task_repo.list_by_state(TaskStatus.MANUAL_REVIEW)
    manual_review_task_ids = {task.id for task in manual_review_tasks}
    error_events = exec_repo.list_events(level=EventLevel.ERROR)
    task_by_id = {
        task.id: task for task in task_repo.list_by_filters()
    }
    queue_by_task = {}
    for item in queue_repo.list_all():
        queue_by_task.setdefault(item.task_id, item)
    screenshots_by_task: dict[str, list[str]] = {}
    for artifact in exec_repo.list_artifacts():
        if artifact.artifact_type.upper() != "SCREENSHOT":
            continue
        screenshots_by_task.setdefault(artifact.task_id, []).append(
            artifact.path
        )

    failed_steps_by_task = {}
    for task in manual_review_tasks:
        failed = [
            step
            for step in workflow_repo.list_steps_by_task(task.id)
            if step.status == StepStatus.FAILED
        ]
        if failed:
            failed_steps_by_task[task.id] = max(
                failed,
                key=lambda step: (step.finished_at or step.started_at, step.id),
            )
    latest_error_by_task = {}
    for event in error_events:
        if event.task_id not in manual_review_task_ids:
            continue
        current = latest_error_by_task.get(event.task_id)
        if current is None or (event.occurred_at, event.id) > (
            current.occurred_at,
            current.id,
        ):
            latest_error_by_task[event.task_id] = event

    items: list[ExceptionView] = [
        ExceptionView(
            id=event.id,
            task_id=event.task_id,
            level=event.level,
            message=event.message,
            occurred_at=event.occurred_at,
            drama_name=(
                task_by_id[event.task_id].drama_name
                if event.task_id in task_by_id
                else None
            ),
            platform=(
                task_by_id[event.task_id].platform
                if event.task_id in task_by_id
                else None
            ),
            error_type=event.event_type,
            step=_exception_step(
                None, event, task_by_id.get(event.task_id)
            ),
            failure_code=_failure_code(None, event),
            failure_details=_failure_details(None, event),
            retry_safe=(
                queue_by_task[event.task_id].retry_safe
                if event.task_id in queue_by_task
                else None
            ),
            screenshots=screenshots_by_task.get(event.task_id) or None,
        )
        for event in error_events
        if event.task_id not in manual_review_task_ids
        and (
            event.task_id not in task_by_id
            or task_by_id[event.task_id].status not in _RESOLVED_TASK_STATUSES
        )
    ]
    items.extend(
        ExceptionView(
            id=_exception_id(
                task,
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
            ),
            task_id=task.id,
            level=TaskStatus.MANUAL_REVIEW,
            message=_exception_message(
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
            ),
            occurred_at=_exception_time(
                task,
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
            ),
            drama_name=task.drama_name,
            platform=task.platform,
            error_type=_exception_type(
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
            ),
            step=_exception_step(
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
                task,
            ),
            failure_code=_failure_code(
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
            ) or (
                queue_by_task[task.id].failure_code
                if task.id in queue_by_task
                else None
            ),
            failure_details=_failure_details(
                failed_steps_by_task.get(task.id),
                latest_error_by_task.get(task.id),
            ),
            retry_safe=(
                queue_by_task[task.id].retry_safe
                if task.id in queue_by_task
                else None
            ),
            screenshots=screenshots_by_task.get(task.id) or None,
        )
        for task in manual_review_tasks
    )
    items.sort(key=lambda item: (item.occurred_at, item.id), reverse=True)
    return items


def _exception_id(task, failed_step, error_event) -> str:
    return failed_step.id if failed_step else error_event.id if error_event else task.id


def _exception_message(failed_step, error_event) -> str:
    if failed_step:
        return failed_step.error_message or _MANUAL_REVIEW_MESSAGE
    return error_event.message if error_event else _MANUAL_REVIEW_MESSAGE


def _exception_time(task, failed_step, error_event):
    if failed_step:
        return failed_step.finished_at or failed_step.started_at or task.updated_at
    if error_event:
        return error_event.occurred_at
    return task.updated_at


def _exception_type(failed_step, error_event) -> str:
    if failed_step:
        return failed_step.error_code or TaskStatus.MANUAL_REVIEW
    return error_event.event_type if error_event else TaskStatus.MANUAL_REVIEW


def _exception_step(failed_step, error_event, task=None) -> str:
    context = error_event.context_json if error_event else None
    source = (
        failed_step.step_name
        if failed_step
        else (context or {}).get("step_name")
        or (context or {}).get("current_stage")
        or (
            task.current_stage
            if task is not None and task.status == TaskStatus.MANUAL_REVIEW
            and task.current_stage != "WAITING_AVAILABLE_TIME"
            else None
        )
        or (error_event.event_type if error_event else None)
    )
    return _EVENT_STEP_MAP.get(source, source) if source else "人工复核"


def _failure_code(failed_step, error_event) -> str | None:
    if failed_step:
        return failed_step.error_code
    context = error_event.context_json if error_event else None
    return (context or {}).get("failure_code") or (context or {}).get("error_code")


def _failure_details(failed_step, error_event) -> dict | None:
    if failed_step:
        return None
    context = error_event.context_json if error_event else None
    details = (context or {}).get("details")
    return details if isinstance(details, dict) else None

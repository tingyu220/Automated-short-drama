"""任务 API 路由：列表、详情、手动入队。"""
from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone

import json
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.application.services.task_control_service import retry_task
from backend.application.services.delivery_scheduler import DeliveryScheduler
from backend.bootstrap.adapters import build_scheduler_feishu
from backend.domain.common.timezones import SHANGHAI_TZ, as_utc
from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.domain.common.timezones import SHANGHAI_TZ
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.rules.drama_match import normalize_drama_name
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
from backend.infrastructure.database.repositories.workflow_repository import (
    SqlAlchemyWorkflowRepository,
)
from backend.infrastructure.database.session import get_session
from backend.infrastructure.config.settings import Settings
from backend.interfaces.api.schemas import (
    QueueItemView,
    StepRunView,
    TaskCreateBody,
    TaskDetail,
    TaskEnqueueBody,
    DramaMatchConfirmationBody,
    TaskSummary,
)

router = APIRouter(tags=["tasks"])

_TERMINAL_STATES = frozenset(
    {QueueState.COMPLETED, QueueState.CANCELLED, QueueState.DRY_RUN}
)


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
        end_type=task.end_type,
        available_time=task.available_time,
        status=task.status,
        owner=task.owner,
        queue_state=item.state if item else None,
        current_stage=task.current_stage,
        target_stage=task.target_stage,
        updated_at=task.updated_at,
    )


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(
    date: date_type | None = Query(default=None, description="YYYY-MM-DD"),
    platform: str | None = None,
    status: str | None = None,
    q: str | None = None,
    end_type: str | None = None,
    db: Session = Depends(get_db),
):
    """按日期/平台/状态/剧名/端类型筛选任务，按 available_time 降序。"""
    available_from = None
    available_to = None
    if date is not None:
        # 业务日界按东八区计算，落库时间为 naive UTC，因此转回 naive 后查询。
        available_from = datetime.combine(
            date, time.min, tzinfo=SHANGHAI_TZ
        ).astimezone(timezone.utc).replace(tzinfo=None)
        available_to = available_from + timedelta(days=1)

    tasks = SqlAlchemyTaskRepository(db).list_by_filters(
        platform=platform,
        status=status,
        q=q,
        end_type=end_type,
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


@router.post("/tasks", response_model=TaskSummary, status_code=201)
def create_task(
    body: TaskCreateBody,
    db: Session = Depends(get_db),
):
    """直接创建单个任务，用于小程序产线手动输入剧目等场景。"""
    import uuid as uuid_mod
    from backend.domain.tasks.end_type import EndType
    from backend.domain.tasks.source_key import build_task_source_key

    available_time = body.available_time or datetime.now(timezone.utc)
    if available_time.tzinfo is None:
        available_time = available_time.replace(tzinfo=timezone.utc)
    task = DramaTask(
        id=str(uuid_mod.uuid4()),
        drama_name=body.drama_name,
        platform=body.platform,
        end_type=EndType.validate(body.end_type),
        available_time=available_time,
        source_key=build_task_source_key(
            body.drama_name, body.platform,
            available_time.strftime("%Y/%m/%d %H:%M"),
            body.end_type,
        ),
    )
    task = SqlAlchemyTaskRepository(db).add(task)
    db.commit()
    return _to_summary(task, None)


@router.post("/tasks/scan")
def scan_tasks(db: Session = Depends(get_db)):
    """手动执行一次剧目扫描，作为每小时调度的人工兜底。"""
    try:
        feishu, mode = build_scheduler_feishu(Settings())
        result = DeliveryScheduler(
            feishu=feishu,
            task_repo=SqlAlchemyTaskRepository(db),
            queue_repo=SqlAlchemyQueueRepository(db),
        ).tick(datetime.now(timezone.utc))
        db.commit()
        return {
            "day": result.day,
            "created_tasks": result.created_tasks,
            "updated_tasks": result.updated_tasks,
            "enqueued": result.enqueued,
            "skipped": result.skipped,
            "mode": mode,
        }
    except Exception:
        db.rollback()
        raise


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)):
    """返回任务详情，不存在时抛 404。"""
    task = SqlAlchemyTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError(f"DramaTask {task_id} not found")

    queue_items = SqlAlchemyQueueRepository(db).list_by_task(task_id)
    item = queue_items[0] if queue_items else None
    ledgers = SqlAlchemyLedgerRepository(db).list_by_task(task_id)
    steps = SqlAlchemyWorkflowRepository(db).list_steps_by_task(task_id)
    candidates = _latest_drama_match_candidates(db, task_id)

    summary = _to_summary(task, item)
    return TaskDetail(
        **summary.model_dump(),
        queue_item_id=item.id if item else None,
        attempt_count=item.attempt_count if item else None,
        claimed_by=item.claimed_by if item else None,
        lease_until=item.lease_until if item else None,
        failure_code=item.failure_code if item else None,
        retry_safe=item.retry_safe if item else None,
        ledger_id=ledgers[0].id if ledgers else None,
        link_set=dict(task.link_set),
        delivery_drama_id=task.delivery_drama_id,
        promotion_configs=dict(task.promotion_configs),
        steps=[StepRunView.model_validate(step) for step in steps],
        drama_match_candidates=candidates,
        confirmed_drama_match=(
            task.confirmed_drama_match.to_dict()
            if task.confirmed_drama_match is not None
            else None
        ),
    )


@router.post(
    "/tasks/{task_id}/confirm-drama-match", response_model=QueueItemView
)
def confirm_drama_match(
    task_id: str,
    body: DramaMatchConfirmationBody,
    db: Session = Depends(get_db),
):
    """保存人工确认的番茄候选并将人工处理任务重新入队。"""
    task_repo = SqlAlchemyTaskRepository(db)
    task = task_repo.get(task_id)
    if task is None:
        raise NotFoundError(f"DramaTask {task_id} not found")
    if task.platform != "TOMATO":
        raise ConflictError("只有番茄任务支持剧目候选确认")
    candidates = _latest_drama_match_candidates(db, task_id)
    selected = next(
        (item for item in candidates if item.get("locator_key") == body.locator_key),
        None,
    )
    if selected is None:
        raise ConflictError("候选不在最近一次匹配失败证据中")
    if not selected.get("drama_name") or normalize_drama_name(
        str(selected["drama_name"])
    ) != normalize_drama_name(task.drama_name):
        raise ConflictError("只能确认剧名完全一致的候选")
    try:
        available_minute = datetime.fromisoformat(str(selected["minute"]))
    except ValueError as exc:
        raise ConflictError("候选时间无法解析，不能确认") from exc
    if available_minute.tzinfo is None:
        raise ConflictError("候选时间缺少时区，不能确认")
    task.confirmed_drama_match = ConfirmedDramaMatch(
        locator_key=body.locator_key,
        available_minute=available_minute.astimezone(SHANGHAI_TZ),
        confirmed_at=datetime.now(timezone.utc),
    )
    task.status = TaskStatus.READY
    task_repo.update(task)
    queue_repo = SqlAlchemyQueueRepository(db)
    item = next(
        (candidate for candidate in queue_repo.list_by_task(task_id)
         if candidate.state == QueueState.MANUAL_REVIEW),
        None,
    )
    if item is None:
        raise ConflictError("任务当前没有人工处理队列项")
    item = retry_task(queue_repo, task_repo, item.id)
    return QueueItemView.model_validate(item)


@router.post("/tasks/{task_id}/enqueue", response_model=QueueItemView)
def enqueue_task(
    task_id: str,
    response: Response,
    body: TaskEnqueueBody | None = None,
    db: Session = Depends(get_db),
):
    """创建或复用队列项；已存在活动项时返回 409。"""
    task = SqlAlchemyTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError(f"DramaTask {task_id} not found")

    if (
        task.link_status == "DRAMA_MISMATCH"
        and task.confirmed_drama_match is None
        and not _has_single_in_tolerance_candidate(db, task_id)
    ):
        raise ConflictError("请先确认番茄候选后再继续执行")

    was_dry_run = task.status == TaskStatus.DRY_RUN
    task.target_stage = (body or TaskEnqueueBody()).target_stage
    if task.status in {
        TaskStatus.DRY_RUN,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    }:
        task.status = TaskStatus.WAITING_TIME
    if was_dry_run:
        # 演练产物不能带入真实执行，重新入队时强制从来源重新准备。
        task.link_set = {}
        task.link_status = "NOT_STARTED"
        task.delivery_drama_id = ""
        task.promotion_configs = {}
        task.current_stage = "WAITING_AVAILABLE_TIME"
    SqlAlchemyTaskRepository(db).update(task)
    queue_repo = SqlAlchemyQueueRepository(db)
    items = queue_repo.list_by_task(task_id)
    active_item = next(
        (candidate for candidate in items if candidate.state not in _TERMINAL_STATES),
        None,
    )
    if active_item is not None:
        if active_item.state in {
            QueueState.MANUAL_REVIEW,
            QueueState.FAILED,
            QueueState.RETRY_WAIT,
        }:
            item = retry_task(
                queue_repo, SqlAlchemyTaskRepository(db), active_item.id
            )
            return QueueItemView.model_validate(item)
        raise ConflictError(
            f"任务 {task_id} 已存在活动队列项 {active_item.id}（{active_item.state}）"
        )

    if items:
        item = items[0]
        item.state = QueueState.WAITING_TIME
        item.available_at = as_utc(task.available_time)
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
                available_at=as_utc(task.available_time),
            )
        )
        response.status_code = 201

    return QueueItemView.model_validate(item)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, db: Session = Depends(get_db)):
    """删除任务及其关联的队列项、执行事件、产物、工作流和台账。"""
    from backend.infrastructure.database.models.task import (
        DramaTaskRecord,
        QueueItemRecord,
        TaskLedgerRecord,
        WorkflowRunRecord,
    )
    from backend.infrastructure.database.models.execution import (
        ExecutionArtifactRecord,
        ExecutionEventRecord,
    )

    task = db.get(DramaTaskRecord, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"DramaTask {task_id} not found")

    db.execute(delete(ExecutionArtifactRecord).where(ExecutionArtifactRecord.task_id == task_id))
    db.execute(delete(ExecutionEventRecord).where(ExecutionEventRecord.task_id == task_id))
    workflow_ids = [
        r[0] for r in db.execute(
            select(WorkflowRunRecord.id).where(WorkflowRunRecord.task_id == task_id)
        ).all()
    ]
    if workflow_ids:
        from backend.infrastructure.database.models.task import StepRunRecord
        db.execute(delete(StepRunRecord).where(StepRunRecord.workflow_run_id.in_(workflow_ids)))
        db.execute(delete(WorkflowRunRecord).where(WorkflowRunRecord.task_id == task_id))
    db.execute(delete(TaskLedgerRecord).where(TaskLedgerRecord.task_id == task_id))
    db.execute(delete(QueueItemRecord).where(QueueItemRecord.task_id == task_id))
    db.delete(task)
    db.commit()


def _latest_drama_match_candidates(db: Session, task_id: str) -> list[dict]:
    """从最近一次匹配失败事件提取候选证据。"""
    events = SqlAlchemyExecutionRepository(db).list_events(task_id=task_id)
    for event in events:
        context = event.context_json or {}
        if event.event_type in {"MANUAL_REVIEW", "LINK_EXTRACTION"} and context.get(
            "candidates"
        ):
            return list(context["candidates"])
    return []


def _has_single_in_tolerance_candidate(db: Session, task_id: str) -> bool:
    """允许历史上因旧严格规则失败、现已落入容差窗口的任务自动重试。"""
    events = SqlAlchemyExecutionRepository(db).list_events(task_id=task_id)
    for event in events:
        context = event.context_json or {}
        candidates = context.get("candidates") or []
        expected_raw = context.get("expected_minute")
        if not expected_raw or len(candidates) != 1:
            continue
        try:
            expected = datetime.fromisoformat(str(expected_raw))
            candidate = datetime.fromisoformat(str(candidates[0]["minute"]))
        except (KeyError, TypeError, ValueError):
            continue
        if expected.tzinfo is None or candidate.tzinfo is None:
            continue
        difference = abs(
            int(
                (
                    candidate.astimezone(SHANGHAI_TZ)
                    - expected.astimezone(SHANGHAI_TZ)
                ).total_seconds()
                // 60
            )
        )
        if difference <= 5:
            return True
    return False

"""Worker 执行循环服务 —— 认领任务执行、写事件、生成台账。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from backend.application.services.completion_service import complete_task
from backend.domain.errors.domain_error import NotFoundError
from backend.domain.execution.execution_event import EventLevel, ExecutionEvent
from backend.domain.ports.repositories import (
    ExecutionRepository,
    LedgerRepository,
    QueueRepository,
    TaskRepository,
)
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.queue.state_machine import QueueStateMachine
from backend.domain.tasks.drama_task import DramaTask, TaskStatus

STATUS_COMPLETED = "COMPLETED"
STATUS_MANUAL_REVIEW = "MANUAL_REVIEW"
STATUS_FAILED = "FAILED"


@dataclass
class ExecutionOutcome:
    """Executor 执行结果。"""

    status: str
    external_task_id: str | None = None
    ledger_fields: dict = field(default_factory=dict)
    events: list[ExecutionEvent] = field(default_factory=list)


@dataclass
class CycleResult:
    """单次 Worker 执行循环结果。"""

    queue_item_id: str
    final_queue_state: str
    ledger_id: str | None = None
    event_count: int = 0


class WorkerExecutionService:
    """领取任务执行闭环：状态流转、事件落库、完成台账。"""

    def __init__(
        self,
        executor: Callable[[DramaTask, QueueItem], ExecutionOutcome],
        queue_repo: QueueRepository,
        task_repo: TaskRepository,
        ledger_repo: LedgerRepository,
        event_repo: ExecutionRepository,
        worker_id: str,
    ) -> None:
        self._executor = executor
        self._queue_repo = queue_repo
        self._task_repo = task_repo
        self._ledger_repo = ledger_repo
        self._event_repo = event_repo
        self._worker_id = worker_id

    def process_claimed(self, item: QueueItem, now: datetime) -> CycleResult:
        """处理已认领任务；仅 CLAIMED 状态执行，其余直接跳过。"""
        if item.state != QueueState.CLAIMED:
            return CycleResult(
                queue_item_id=item.id,
                final_queue_state=item.state,
            )

        item.state = QueueStateMachine.transition(
            item.state, QueueState.RUNNING
        )
        self._queue_repo.update(item)

        task = self._task_repo.get(item.task_id)
        if task is None:
            raise NotFoundError(f"DramaTask {item.task_id} not found")
        task.status = TaskStatus.RUNNING
        self._task_repo.update(task)

        outcome = self._invoke_executor(task, item)
        events = self._build_events(task, outcome, now)
        for execution_event in events:
            self._event_repo.add_event(execution_event)

        if outcome.status == STATUS_COMPLETED:
            ledger = self._complete(item, outcome)
            return CycleResult(
                queue_item_id=item.id,
                final_queue_state=item.state,
                ledger_id=ledger.id,
                event_count=len(events),
            )

        if outcome.status not in (STATUS_MANUAL_REVIEW, STATUS_FAILED):
            raise ValueError(f"未知执行结果状态: {outcome.status}")
        item.state = QueueStateMachine.transition(item.state, outcome.status)
        self._queue_repo.update(item)
        task.status = outcome.status
        self._task_repo.update(task)
        return CycleResult(
            queue_item_id=item.id,
            final_queue_state=item.state,
            event_count=len(events),
        )

    def _complete(self, item: QueueItem, outcome: ExecutionOutcome):
        """COMPLETED：复用完成服务出队并生成台账。"""
        ledger_fields = dict(outcome.ledger_fields)
        if outcome.external_task_id is not None:
            ledger_fields["external_task_id"] = outcome.external_task_id
        ledger = complete_task(
            item.id,
            self._worker_id,
            self._queue_repo,
            self._task_repo,
            self._ledger_repo,
            ledger_fields,
        )
        item.state = QueueState.COMPLETED
        return ledger

    def _invoke_executor(
        self, task: DramaTask, item: QueueItem
    ) -> ExecutionOutcome:
        """调用 executor；异常视为 MANUAL_REVIEW 并生成 ERROR 事件。"""
        try:
            return self._executor(task, item)
        except Exception as exc:
            return ExecutionOutcome(
                status=STATUS_MANUAL_REVIEW,
                events=[
                    ExecutionEvent(
                        task_id=task.id,
                        event_type="EXECUTION_ERROR",
                        message=f"executor 异常: {exc}",
                        level=EventLevel.ERROR,
                    )
                ],
            )

    @staticmethod
    def _build_events(
        task: DramaTask,
        outcome: ExecutionOutcome,
        now: datetime,
    ) -> list[ExecutionEvent]:
        """组合 outcome 事件；非完成结果保证至少一条 ERROR 事件。"""
        events = list(outcome.events)
        if (
            outcome.status != STATUS_COMPLETED
            and not any(e.level == EventLevel.ERROR for e in events)
        ):
            events.append(
                ExecutionEvent(
                    task_id=task.id,
                    event_type="STATUS_CHANGED",
                    message=f"执行结果 {outcome.status}，队列与任务转入 {outcome.status}",
                    level=EventLevel.ERROR,
                    occurred_at=now,
                )
            )
        return events


def mock_worker_executor() -> Callable[[DramaTask, QueueItem], ExecutionOutcome]:
    """默认 Mock executor：直接返回 COMPLETED（Task 10.4 替换真实 executor）。"""

    def execute(task: DramaTask, _item: QueueItem) -> ExecutionOutcome:
        return ExecutionOutcome(
            status=STATUS_COMPLETED,
            external_task_id="mock-external-1",
            ledger_fields={
                "album_id": "album-mock",
                "product_id": "product-mock",
                "task_name": "mock-task",
                "rule_version": "1.0",
                "config_version": "1.0",
            },
            events=[
                ExecutionEvent(
                    task_id=task.id,
                    event_type="MOCK_EXECUTED",
                    message="Mock 执行完成，Task 10.4 替换真实 executor",
                    level=EventLevel.INFO,
                )
            ],
        )

    return execute

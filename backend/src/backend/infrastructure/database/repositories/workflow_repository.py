"""WorkflowRun/StepRun SQLAlchemy 仓储。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.workflow.step_run import StepRun, StepStatus
from backend.domain.workflow.workflow_run import WorkflowRun
from backend.infrastructure.database.models.task import (
    StepRunRecord,
    WorkflowRunRecord,
)


class SqlAlchemyWorkflowRepository:
    """把阶段执行记录转换为领域模型。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_workflow(self, run: WorkflowRun) -> WorkflowRun:
        record = WorkflowRunRecord(
            id=run.id or str(uuid.uuid4()),
            task_id=run.task_id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_workflow(record)

    def get_workflow(self, run_id: str) -> WorkflowRun | None:
        record = self._session.get(WorkflowRunRecord, run_id)
        return self._to_workflow(record) if record else None

    def update_workflow(self, run: WorkflowRun) -> WorkflowRun:
        record = self._session.get(WorkflowRunRecord, run.id)
        if record is None:
            raise ValueError(f"WorkflowRun {run.id} not found")
        record.status = run.status
        record.started_at = run.started_at
        record.finished_at = run.finished_at
        self._session.flush()
        return self._to_workflow(record)

    def add_step(self, step: StepRun) -> StepRun:
        record = StepRunRecord(
            id=step.id or str(uuid.uuid4()),
            workflow_run_id=step.workflow_run_id,
            step_name=step.step_name,
            status=step.status,
            started_at=step.started_at,
            finished_at=step.finished_at,
            result_json=(
                json.dumps(step.result_json, ensure_ascii=False)
                if step.result_json is not None
                else None
            ),
            error_code=step.error_code,
            error_message=step.error_message,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_step(record)

    def get_step(self, step_id: str) -> StepRun | None:
        record = self._session.get(StepRunRecord, step_id)
        return self._to_step(record) if record else None

    def update_step(self, step: StepRun) -> StepRun:
        record = self._session.get(StepRunRecord, step.id)
        if record is None:
            raise ValueError(f"StepRun {step.id} not found")
        record.status = step.status
        record.started_at = step.started_at
        record.finished_at = step.finished_at
        record.result_json = (
            json.dumps(step.result_json, ensure_ascii=False)
            if step.result_json is not None
            else None
        )
        record.error_code = step.error_code
        record.error_message = step.error_message
        self._session.flush()
        return self._to_step(record)

    def list_steps_by_workflow(self, workflow_run_id: str) -> list[StepRun]:
        records = self._session.execute(
            select(StepRunRecord)
            .where(StepRunRecord.workflow_run_id == workflow_run_id)
            .order_by(StepRunRecord.started_at, StepRunRecord.id)
        ).scalars().all()
        return [self._to_step(record) for record in records]

    def start_step(self, task_id: str, step_name: str) -> StepRun:
        now = datetime.now(timezone.utc)
        workflow = self.add_workflow(
            WorkflowRun(
                id=str(uuid.uuid4()),
                task_id=task_id,
                status="RUNNING",
                started_at=now,
            )
        )
        return self.add_step(
            StepRun(
                workflow_run_id=workflow.id,
                step_name=step_name,
                status=StepStatus.RUNNING,
                started_at=now,
            )
        )

    def finish_step(self, step: StepRun, result: dict | None = None) -> StepRun:
        step.status = StepStatus.COMPLETED
        step.finished_at = datetime.now(timezone.utc)
        step.result_json = result
        return self.update_step(step)

    def fail_step(
        self, step: StepRun, error_code: str, error_message: str
    ) -> StepRun:
        step.status = StepStatus.FAILED
        step.finished_at = datetime.now(timezone.utc)
        step.error_code = error_code
        step.error_message = error_message
        return self.update_step(step)

    def list_steps_by_task(self, task_id: str) -> list[StepRun]:
        workflow_ids = self._session.execute(
            select(WorkflowRunRecord.id)
            .where(WorkflowRunRecord.task_id == task_id)
            .order_by(WorkflowRunRecord.started_at, WorkflowRunRecord.id)
        ).scalars().all()
        if not workflow_ids:
            return []
        records = self._session.execute(
            select(StepRunRecord)
            .where(StepRunRecord.workflow_run_id.in_(workflow_ids))
            .order_by(StepRunRecord.started_at, StepRunRecord.id)
        ).scalars().all()
        return [self._to_step(record) for record in records]

    @staticmethod
    def _to_workflow(record: WorkflowRunRecord) -> WorkflowRun:
        return WorkflowRun(
            id=record.id,
            task_id=record.task_id,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )

    @staticmethod
    def _to_step(record: StepRunRecord) -> StepRun:
        try:
            result = json.loads(record.result_json or "null")
        except json.JSONDecodeError:
            result = None
        return StepRun(
            id=record.id,
            workflow_run_id=record.workflow_run_id,
            step_name=record.step_name,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
            result_json=result if isinstance(result, dict) else None,
            error_code=record.error_code,
            error_message=record.error_message,
        )

"""Repository Protocol 接口 —— Domain 层不依赖 SQLAlchemy."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from backend.domain.tasks.drama_task import DramaTask
from backend.domain.queue.queue_item import QueueItem
from backend.domain.workflow.workflow_run import WorkflowRun
from backend.domain.workflow.step_run import StepRun
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.execution.execution_artifact import ExecutionArtifact
from backend.domain.execution.execution_event import ExecutionEvent
from backend.domain.rules.config_change_log import ConfigChangeLog
from backend.domain.rules.config_snapshot import ConfigSnapshot
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.rules.rule_set import RuleSet
from backend.domain.rules.rule_version import RuleVersion
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.worker.worker_lease import WorkerLease


class TaskRepository(Protocol):
    """DramaTask 仓储协议."""

    def add(self, task: DramaTask) -> DramaTask: ...
    def get(self, task_id: str) -> DramaTask | None: ...
    def update(self, task: DramaTask) -> DramaTask: ...
    def list_by_state(self, state: str) -> list[DramaTask]: ...
    def list_by_filters(
        self,
        *,
        platform: str | None = None,
        status: str | None = None,
        q: str | None = None,
        available_from: datetime | None = None,
        available_to: datetime | None = None,
    ) -> list[DramaTask]: ...


class QueueRepository(Protocol):
    """QueueItem 仓储协议."""

    def add(self, item: QueueItem) -> QueueItem: ...
    def get(self, item_id: str) -> QueueItem | None: ...
    def update(self, item: QueueItem) -> QueueItem: ...
    def list_by_state(self, state: str) -> list[QueueItem]: ...
    def list_all(self) -> list[QueueItem]: ...
    def list_by_task(self, task_id: str) -> list[QueueItem]: ...
    def claim_next(
        self,
        worker_id: str,
        lease_seconds: int,
        now: datetime,
    ) -> QueueItem | None: ...
    def find_expired(self, now: datetime) -> list[QueueItem]: ...
    def release_claimed(
        self,
        item_id: str,
        worker_id: str,
    ) -> bool: ...
    def recover_expired(
        self,
        now: datetime,
        max_attempts: int,
    ) -> tuple[list[QueueItem], list[QueueItem]]: ...


class WorkflowRepository(Protocol):
    """WorkflowRun / StepRun 仓储协议."""

    def add_workflow(self, run: WorkflowRun) -> WorkflowRun: ...
    def get_workflow(self, run_id: str) -> WorkflowRun | None: ...
    def update_workflow(self, run: WorkflowRun) -> WorkflowRun: ...
    def add_step(self, step: StepRun) -> StepRun: ...
    def get_step(self, step_id: str) -> StepRun | None: ...
    def update_step(self, step: StepRun) -> StepRun: ...
    def list_steps_by_workflow(self, workflow_run_id: str) -> list[StepRun]: ...


class LedgerRepository(Protocol):
    """TaskLedger 仓储协议."""

    def add(self, ledger: TaskLedger) -> TaskLedger: ...
    def get(self, ledger_id: str) -> TaskLedger | None: ...
    def update(self, ledger: TaskLedger) -> TaskLedger: ...
    def list_by_task(self, task_id: str) -> list[TaskLedger]: ...
    def list_all(self) -> list[TaskLedger]: ...


class ExecutionRepository(Protocol):
    """ExecutionEvent / ExecutionArtifact 仓储协议。"""

    def add_event(self, event: ExecutionEvent) -> ExecutionEvent: ...
    def list_events(
        self,
        *,
        task_id: str | None = None,
        level: str | None = None,
    ) -> list[ExecutionEvent]: ...
    def list_artifacts(
        self,
        *,
        task_id: str | None = None,
    ) -> list[ExecutionArtifact]: ...
    def delete_artifact(self, artifact_id: str) -> None: ...


class RuleRepository(Protocol):
    """RuleSet / RuleVersion / ConfigChangeLog 仓储协议."""

    def add_rule_set(self, rule_set: RuleSet) -> RuleSet: ...
    def get_rule_set(self, rule_set_id: str) -> RuleSet | None: ...
    def get_rule_set_by_key(self, key: str) -> RuleSet | None: ...
    def update_rule_set(self, rule_set: RuleSet) -> RuleSet: ...
    def list_rule_sets(self) -> list[RuleSet]: ...
    def add_rule_version(self, version: RuleVersion) -> RuleVersion: ...
    def update_rule_version(self, version: RuleVersion) -> RuleVersion: ...
    def list_rule_versions(self, rule_set_id: str) -> list[RuleVersion]: ...
    def append_change_log(self, log: ConfigChangeLog) -> ConfigChangeLog: ...


class PriceRuleRepository(Protocol):
    """TemplatePriceRule 仓储协议."""

    def list_template_price_rules(self) -> list[TemplatePriceRule]: ...


class MaterialRuleRepository(Protocol):
    """MaterialRuleRange 仓储协议."""

    def list_material_rule_ranges(self) -> list[MaterialRuleRange]: ...


class SnapshotRepository(Protocol):
    """ConfigSnapshot 仓储协议."""

    def get_rule_version(self, rule_version_id: str) -> RuleVersion | None: ...
    def add(self, snapshot: ConfigSnapshot) -> ConfigSnapshot: ...
    def get_by_task(self, task_id: str) -> ConfigSnapshot | None: ...


class ChangeLogRepository(Protocol):
    """ConfigChangeLog 仓储协议."""

    def add(self, log: ConfigChangeLog) -> ConfigChangeLog: ...


class WorkerLeaseRepository(Protocol):
    """Worker 租约仓储协议。"""

    def acquire(
        self,
        worker_id: str,
        host: str,
        pid: int,
        lease_until: datetime,
        heartbeat_at: datetime,
    ) -> bool: ...
    def heartbeat(
        self,
        worker_id: str,
        host: str,
        pid: int,
        lease_until: datetime,
        heartbeat_at: datetime,
    ) -> WorkerLease: ...
    def release(self, worker_id: str) -> bool: ...
    def is_active(self, worker_id: str, now: datetime) -> bool: ...
    def list_expired(self, now: datetime) -> list[WorkerLease]: ...

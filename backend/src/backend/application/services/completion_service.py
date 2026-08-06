"""任务完成出队与台账服务."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.ports.repositories import (
    LedgerRepository,
    QueueRepository,
    TaskRepository,
)
from backend.domain.queue.queue_item import QueueState
from backend.domain.queue.state_machine import QueueStateMachine
from backend.domain.tasks.drama_task import TaskStatus


def complete_task(
    queue_item_id: str,
    worker_id: str,
    queue_repo: QueueRepository,
    task_repo: TaskRepository,
    ledger_repo: LedgerRepository,
    ledger_fields: dict | None = None,
) -> TaskLedger:
    """完成出队：校验归属、迁移状态、更新 DramaTask、生成台账。

    Args:
        queue_item_id: 队列项 ID。
        worker_id: 完成该任务的 worker。
        queue_repo: QueueRepository 实现（注入）。
        task_repo: TaskRepository 实现（注入）。
        ledger_repo: LedgerRepository 实现（注入）。
        ledger_fields: 台账补充字段（album_id / product_id / external_task_id /
                       task_name / rule_version / config_version）。

    Returns:
        创建好的 TaskLedger。

    Raises:
        NotFoundError: 队列项不存在或关联 DramaTask 不存在。
        ConflictError: claimed_by 不匹配或状态不是 CLAIMED/RUNNING。
    """
    # 1. 读取队列项
    item = queue_repo.get(queue_item_id)
    if item is None:
        raise NotFoundError(f"QueueItem {queue_item_id} not found")

    # 2. 校验 claimant
    if item.claimed_by != worker_id:
        raise ConflictError(
            f"QueueItem {queue_item_id} 由 {item.claimed_by} 认领，"
            f"而非 {worker_id}"
        )

    # 3. 校验状态
    if item.state not in (QueueState.CLAIMED, QueueState.RUNNING):
        raise ConflictError(
            f"QueueItem {queue_item_id} 状态为 {item.state}，"
            f"不允许完成出队"
        )

    # 4. 状态迁移 -> COMPLETED
    item.state = QueueStateMachine.transition(item.state, QueueState.COMPLETED)
    queue_repo.update(item)

    # 5. 读取并更新关联 DramaTask
    task = task_repo.get(item.task_id)
    if task is None:
        raise NotFoundError(f"DramaTask {item.task_id} not found")
    task.status = TaskStatus.COMPLETED
    task_repo.update(task)

    # 6. 创建台账
    fields = ledger_fields or {}
    now = datetime.now(timezone.utc)
    ledger = TaskLedger(
        id=str(uuid.uuid4()),
        task_id=task.id,
        drama_name=task.drama_name,
        platform=task.platform,
        final_status="COMPLETED",
        completed_at=now,
        album_id=fields.get("album_id", ""),
        product_id=fields.get("product_id", ""),
        external_task_id=fields.get("external_task_id", ""),
        task_name=fields.get("task_name", ""),
        rule_version=fields.get("rule_version", ""),
        config_version=fields.get("config_version", ""),
    )
    return ledger_repo.add(ledger)

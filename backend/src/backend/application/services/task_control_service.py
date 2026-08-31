"""队列控制服务：暂停、恢复、取消、重试、人工处理."""
from __future__ import annotations

from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.ports.repositories import QueueRepository, TaskRepository
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.queue.state_machine import QueueStateMachine
from backend.domain.tasks.drama_task import TaskStatus


def _get_item(queue_repo: QueueRepository, queue_item_id: str) -> QueueItem:
    """读取队列项，不存在抛 NotFoundError。"""
    item = queue_repo.get(queue_item_id)
    if item is None:
        raise NotFoundError(f"QueueItem {queue_item_id} not found")
    return item


def _require_worker(item: QueueItem, worker_id: str) -> None:
    """校验领取者与调用方一致，否则抛 ConflictError。"""
    if item.claimed_by != worker_id:
        raise ConflictError(
            f"QueueItem {item.id} 由 {item.claimed_by} 认领，而非 {worker_id}"
        )


def _clear_claim(item: QueueItem) -> None:
    """清空领取与租约字段。"""
    item.claimed_by = None
    item.lease_until = None


def _sync_task_status(
    task_repo: TaskRepository,
    task_id: str,
    status: str,
) -> None:
    """联动更新 DramaTask 生命周期状态；任务不存在时保持队列操作可用。"""
    task = task_repo.get(task_id)
    if task is None:
        return
    task.status = status
    task_repo.update(task)


def pause_task(
    queue_repo: QueueRepository,
    task_repo: TaskRepository,
    queue_item_id: str,
    worker_id: str,
) -> QueueItem:
    """暂停队列项：QUEUED/CLAIMED/RUNNING -> PAUSED，清空领取字段。"""
    item = _get_item(queue_repo, queue_item_id)
    if item.state in (QueueState.COMPLETED, QueueState.CANCELLED, QueueState.DRY_RUN):
        raise ConflictError(f"QueueItem {queue_item_id} 已处于终态 {item.state}")
    if item.state in (QueueState.CLAIMED, QueueState.RUNNING):
        _require_worker(item, worker_id)
    item.state = QueueStateMachine.transition(item.state, QueueState.PAUSED)
    _clear_claim(item)
    _sync_task_status(task_repo, item.task_id, TaskStatus.RUNNING)
    return queue_repo.update(item)


def resume_task(
    queue_repo: QueueRepository,
    task_repo: TaskRepository,
    queue_item_id: str,
) -> QueueItem:
    """恢复队列项：PAUSED -> QUEUED。"""
    item = _get_item(queue_repo, queue_item_id)
    if item.state != QueueState.PAUSED:
        raise ConflictError(
            f"QueueItem {queue_item_id} 状态为 {item.state}，不允许恢复"
        )
    item.state = QueueStateMachine.transition(item.state, QueueState.QUEUED)
    _sync_task_status(task_repo, item.task_id, TaskStatus.READY)
    return queue_repo.update(item)


def cancel_task(
    queue_repo: QueueRepository,
    task_repo: TaskRepository,
    queue_item_id: str,
    worker_id: str,
) -> QueueItem:
    """取消队列项：活动状态 -> CANCELLED，清空领取字段。"""
    item = _get_item(queue_repo, queue_item_id)
    if item.state in (QueueState.COMPLETED, QueueState.CANCELLED, QueueState.DRY_RUN):
        raise ConflictError(f"QueueItem {queue_item_id} 已处于终态 {item.state}")
    if item.state in (QueueState.CLAIMED, QueueState.RUNNING):
        _require_worker(item, worker_id)
    item.state = QueueStateMachine.transition(item.state, QueueState.CANCELLED)
    _clear_claim(item)
    _sync_task_status(task_repo, item.task_id, TaskStatus.CANCELLED)
    return queue_repo.update(item)


def retry_task(
    queue_repo: QueueRepository,
    task_repo: TaskRepository,
    queue_item_id: str,
) -> QueueItem:
    """重试队列项：MANUAL_REVIEW/FAILED/RETRY_WAIT -> QUEUED，重置次数并清空领取字段。"""
    item = _get_item(queue_repo, queue_item_id)
    if item.state not in (
        QueueState.MANUAL_REVIEW,
        QueueState.FAILED,
        QueueState.RETRY_WAIT,
    ):
        raise ConflictError(
            f"QueueItem {queue_item_id} 状态为 {item.state}，不允许重试"
        )
    if item.failure_code == "RESULT_UNCERTAIN" and not item.retry_safe:
        raise ConflictError(
            f"QueueItem {queue_item_id} 提交结果不确定，完成外部对账前禁止重试"
        )
    item.state = QueueStateMachine.transition(item.state, QueueState.QUEUED)
    item.attempt_count = 0
    _clear_claim(item)
    item.failure_code = None
    item.retry_safe = False
    _sync_task_status(task_repo, item.task_id, TaskStatus.READY)
    return queue_repo.update(item)


def mark_manual_review(
    queue_repo: QueueRepository,
    task_repo: TaskRepository,
    queue_item_id: str,
    worker_id: str,
) -> QueueItem:
    """转人工处理：CLAIMED/RUNNING -> MANUAL_REVIEW，清空领取字段。"""
    item = _get_item(queue_repo, queue_item_id)
    if item.state not in (QueueState.CLAIMED, QueueState.RUNNING):
        raise ConflictError(
            f"QueueItem {queue_item_id} 状态为 {item.state}，不允许转人工处理"
        )
    _require_worker(item, worker_id)
    item.state = QueueStateMachine.transition(
        item.state, QueueState.MANUAL_REVIEW
    )
    _clear_claim(item)
    _sync_task_status(task_repo, item.task_id, TaskStatus.MANUAL_REVIEW)
    return queue_repo.update(item)

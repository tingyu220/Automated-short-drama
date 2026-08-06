"""队列服务 - 入队、查看、认领等操作."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.queue.state_machine import QueueStateMachine


def enqueue_when_ready(items: list[QueueItem], now: datetime) -> list[QueueItem]:
    """返回 state=WAITING_TIME 且 available_at <= now 的项，副本状态置为 QUEUED。"""
    result: list[QueueItem] = []
    for item in items:
        if item.state == QueueState.WAITING_TIME and item.available_at <= now:
            cp = deepcopy(item)
            cp.state = QueueStateMachine.transition(cp.state, QueueState.QUEUED)
            result.append(cp)
    return result


def peek_next(items: list[QueueItem], limit: int = 1) -> list[QueueItem]:
    """返回前 limit 个 QUEUED 项，按 priority DESC -> available_at ASC -> id ASC 排序。"""
    queued = [item for item in items if item.state == QueueState.QUEUED]
    queued.sort(key=lambda x: (-x.priority, x.available_at, x.id))
    return queued[:limit]


def to_claimed(item: QueueItem, worker_id: str, lease_until: datetime) -> QueueItem:
    """认领 QUEUED 项：状态 QUEUED->CLAIMED，写入 claimed_by 与 lease_until。"""
    cp = deepcopy(item)
    cp.state = QueueStateMachine.transition(cp.state, QueueState.CLAIMED)
    cp.claimed_by = worker_id
    cp.lease_until = lease_until
    return cp

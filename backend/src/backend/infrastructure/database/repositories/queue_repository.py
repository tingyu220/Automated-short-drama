"""QueueRepository SQLAlchemy 实现 —— 包含原子领取 claim_next."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.infrastructure.database.models.task import QueueItemRecord


class SqlAlchemyQueueRepository:
    """QueueRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- Protocol 方法 ----

    def add(self, item: QueueItem) -> QueueItem:
        """新增队列项."""
        record = QueueItemRecord(
            id=item.id,
            task_id=item.task_id,
            state=item.state,
            priority=item.priority,
            available_at=item.available_at,
            claimed_by=item.claimed_by,
            lease_until=item.lease_until,
            attempt_count=item.attempt_count,
            next_run_at=item.next_run_at,
            failure_code=item.failure_code,
            retry_safe=item.retry_safe,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_domain(record)

    def get(self, item_id: str) -> QueueItem | None:
        """按主键查询."""
        record = self._session.get(QueueItemRecord, item_id)
        if record is None:
            return None
        return self._to_domain(record)

    def update(self, item: QueueItem) -> QueueItem:
        """按 id 全量覆盖字段."""
        record = self._session.get(QueueItemRecord, item.id)
        if record is None:
            raise ValueError(f"QueueItem {item.id} not found")
        record.state = item.state
        record.priority = item.priority
        record.available_at = item.available_at
        record.claimed_by = item.claimed_by
        record.lease_until = item.lease_until
        record.attempt_count = item.attempt_count
        record.next_run_at = item.next_run_at
        record.failure_code = item.failure_code
        record.retry_safe = item.retry_safe
        self._session.flush()
        return self._to_domain(record)

    def list_by_state(self, state: str) -> list[QueueItem]:
        """按状态列出队列项."""
        stmt = select(QueueItemRecord).where(QueueItemRecord.state == state)
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    def list_all(self) -> list[QueueItem]:
        """列出全部队列项，按创建时间倒序。"""
        stmt = select(QueueItemRecord).order_by(
            QueueItemRecord.created_at.desc(),
            QueueItemRecord.id.desc(),
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    def list_by_task(self, task_id: str) -> list[QueueItem]:
        """按任务列出队列项，按创建时间倒序。"""
        stmt = (
            select(QueueItemRecord)
            .where(QueueItemRecord.task_id == task_id)
            .order_by(
                QueueItemRecord.created_at.desc(),
                QueueItemRecord.id.desc(),
            )
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    # ---- 扩展方法 ----

    def claim_next(
        self, worker_id: str, lease_seconds: int, now: datetime
    ) -> QueueItem | None:
        """原子领取一个 QUEUED 项：按 priority DESC → available_at ASC → id ASC 取第一条，
        更新为 CLAIMED 并写入 claimed_by、lease_until。

        使用子查询定位 + update returning 保证 SQLite 下的原子性。
        """
        lease_until = now + timedelta(seconds=lease_seconds)

        # 子查询定位最优候选
        subq = (
            select(QueueItemRecord.id)
            .where(QueueItemRecord.state == QueueState.QUEUED)
            .order_by(
                QueueItemRecord.priority.desc(),
                QueueItemRecord.available_at.asc(),
                QueueItemRecord.id.asc(),
            )
            .limit(1)
        ).scalar_subquery()

        # 原子更新 + 返回 id
        stmt = (
            update(QueueItemRecord)
            .where(QueueItemRecord.id == subq)
            .values(
                state=QueueState.CLAIMED,
                claimed_by=worker_id,
                lease_until=lease_until,
            )
            .returning(QueueItemRecord.id)
        )

        result = self._session.execute(stmt)
        claimed_id = result.scalar_one_or_none()
        if claimed_id is None:
            return None

        # 重新查询获取完整 ORM 对象
        record = self._session.execute(
            select(QueueItemRecord).where(QueueItemRecord.id == claimed_id)
        ).scalar_one()
        return self._to_domain(record)

    def find_expired(self, now: datetime) -> list[QueueItem]:
        """查找已过期的 CLAIMED / RUNNING 项（lease_until < now）."""
        stmt = select(QueueItemRecord).where(
            QueueItemRecord.state.in_(
                [QueueState.CLAIMED, QueueState.RUNNING]
            ),
            QueueItemRecord.lease_until < now,
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    def release_claimed(self, item_id: str, worker_id: str) -> bool:
        """条件原子释放：仅当 claimed_by 匹配且状态为 CLAIMED/RUNNING 时置回 QUEUED。"""
        stmt = (
            update(QueueItemRecord)
            .where(
                QueueItemRecord.id == item_id,
                QueueItemRecord.claimed_by == worker_id,
                QueueItemRecord.state.in_(
                    [QueueState.CLAIMED, QueueState.RUNNING]
                ),
            )
            .values(
                state=QueueState.QUEUED,
                claimed_by=None,
                lease_until=None,
            )
            .returning(QueueItemRecord.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    def recover_expired(
        self,
        now: datetime,
        max_attempts: int,
    ) -> tuple[list[QueueItem], list[QueueItem]]:
        """条件原子恢复过期项：未超重试回到 QUEUED，否则转 MANUAL_REVIEW。"""
        expired_where = (
            QueueItemRecord.state.in_(
                [QueueState.CLAIMED, QueueState.RUNNING]
            ),
            QueueItemRecord.lease_until < now,
        )
        requeued_ids: list[str] = []
        manual_ids: list[str] = []

        requeue_stmt = (
            update(QueueItemRecord)
            .where(
                *expired_where,
                QueueItemRecord.attempt_count + 1 <= max_attempts,
            )
            .values(
                state=QueueState.QUEUED,
                attempt_count=QueueItemRecord.attempt_count + 1,
                claimed_by=None,
                lease_until=None,
            )
            .returning(QueueItemRecord.id)
        )
        manual_stmt = (
            update(QueueItemRecord)
            .where(
                *expired_where,
                QueueItemRecord.attempt_count + 1 > max_attempts,
            )
            .values(
                state=QueueState.MANUAL_REVIEW,
                attempt_count=QueueItemRecord.attempt_count + 1,
                claimed_by=None,
                lease_until=None,
            )
            .returning(QueueItemRecord.id)
        )
        requeued_ids = list(self._session.execute(requeue_stmt).scalars().all())
        manual_ids = list(self._session.execute(manual_stmt).scalars().all())

        ids = requeued_ids + manual_ids
        if not ids:
            return [], []
        records = self._session.execute(
            select(QueueItemRecord).where(QueueItemRecord.id.in_(ids))
        ).scalars().all()
        by_id = {record.id: record for record in records}
        requeued = [
            self._to_domain(by_id[item_id]) for item_id in requeued_ids
        ]
        manual = [
            self._to_domain(by_id[item_id]) for item_id in manual_ids
        ]
        return requeued, manual

    # ---- 内部辅助 ----

    @staticmethod
    def _to_domain(record: QueueItemRecord) -> QueueItem:
        """ORM → 领域模型."""
        return QueueItem(
            id=record.id,
            task_id=record.task_id,
            state=record.state,
            priority=record.priority,
            available_at=record.available_at,
            claimed_by=record.claimed_by,
            lease_until=record.lease_until,
            attempt_count=record.attempt_count,
            next_run_at=record.next_run_at,
            failure_code=record.failure_code,
            retry_safe=record.retry_safe,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

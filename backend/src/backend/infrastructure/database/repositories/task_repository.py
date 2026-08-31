"""DramaTask 仓储 SQLAlchemy 实现."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.tasks.drama_task import DramaTask
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.infrastructure.database.models.task import DramaTaskRecord


class SqlAlchemyTaskRepository:
    """TaskRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, task: DramaTask) -> DramaTask:
        """新增任务."""
        record = DramaTaskRecord(
            id=task.id,
            source_key=task.source_key or None,
            sheet_row=task.sheet_row,
            drama_name=task.drama_name,
            platform=task.platform,
            end_type=task.end_type,
            available_time=task.available_time,
            owner=task.owner,
            status=task.status,
            link_set_json=json.dumps(task.link_set, ensure_ascii=False),
            source_links_json=json.dumps(task.source_links, ensure_ascii=False),
            link_status=task.link_status,
            current_stage=task.current_stage,
            target_stage=task.target_stage,
            delivery_drama_id=task.delivery_drama_id,
            promotion_configs_json=json.dumps(
                task.promotion_configs, ensure_ascii=False
            ),
            confirmed_drama_match_json=json.dumps(
                task.confirmed_drama_match.to_dict()
                if task.confirmed_drama_match is not None
                else {},
                ensure_ascii=False,
            ),
        )
        self._session.add(record)
        self._session.flush()
        return self._to_domain(record)

    def get(self, task_id: str) -> DramaTask | None:
        """按主键查询."""
        record = self._session.get(DramaTaskRecord, task_id)
        if record is None:
            return None
        return self._to_domain(record)

    def update(self, task: DramaTask) -> DramaTask:
        """按 id 全量覆盖字段."""
        record = self._session.get(DramaTaskRecord, task.id)
        if record is None:
            raise ValueError(f"DramaTask {task.id} not found")
        record.sheet_row = task.sheet_row
        record.source_key = task.source_key or None
        record.drama_name = task.drama_name
        record.platform = task.platform
        record.end_type = task.end_type
        record.available_time = task.available_time
        record.owner = task.owner
        record.status = task.status
        record.link_set_json = json.dumps(task.link_set, ensure_ascii=False)
        record.source_links_json = json.dumps(task.source_links, ensure_ascii=False)
        record.link_status = task.link_status
        record.current_stage = task.current_stage
        record.target_stage = task.target_stage
        record.delivery_drama_id = task.delivery_drama_id
        record.promotion_configs_json = json.dumps(
            task.promotion_configs, ensure_ascii=False
        )
        record.confirmed_drama_match_json = json.dumps(
            task.confirmed_drama_match.to_dict()
            if task.confirmed_drama_match is not None
            else {},
            ensure_ascii=False,
        )
        self._session.flush()
        return self._to_domain(record)

    def list_by_state(self, state: str) -> list[DramaTask]:
        """按状态列出任务."""
        stmt = select(DramaTaskRecord).where(DramaTaskRecord.status == state)
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    def get_by_source_key(self, source_key: str) -> DramaTask | None:
        """通过稳定来源键查询，飞书顶部插行后仍能命中原任务。"""
        if not source_key:
            return None
        record = self._session.execute(
            select(DramaTaskRecord).where(DramaTaskRecord.source_key == source_key)
        ).scalar_one_or_none()
        return self._to_domain(record) if record is not None else None

    def get_by_drama_and_time(
        self, drama_name: str, available_time: datetime, platform: str
    ) -> DramaTask | None:
        """按剧名+投放时间+平台查询活跃任务，兜底防止 source_key 漂移导致重复。"""
        record = self._session.execute(
            select(DramaTaskRecord).where(
                DramaTaskRecord.drama_name == drama_name,
                DramaTaskRecord.available_time == available_time,
                DramaTaskRecord.platform == platform,
                DramaTaskRecord.status.notin_(
                    ["CANCELLED", "COMPLETED", "DRY_RUN"]
                ),
            )
        ).scalar_one_or_none()
        return self._to_domain(record) if record is not None else None

    def list_by_filters(
        self,
        *,
        platform: str | None = None,
        status: str | None = None,
        q: str | None = None,
        end_type: str | None = None,
        available_from: datetime | None = None,
        available_to: datetime | None = None,
    ) -> list[DramaTask]:
        """按筛选条件列出任务，按 available_time 降序。"""
        stmt = select(DramaTaskRecord)
        if platform:
            stmt = stmt.where(DramaTaskRecord.platform == platform)
        if status:
            stmt = stmt.where(DramaTaskRecord.status == status)
        if end_type:
            stmt = stmt.where(DramaTaskRecord.end_type == end_type)
        if q:
            stmt = stmt.where(DramaTaskRecord.drama_name.like(f"%{q}%"))
        if available_from is not None:
            stmt = stmt.where(DramaTaskRecord.available_time >= available_from)
        if available_to is not None:
            stmt = stmt.where(DramaTaskRecord.available_time < available_to)
        stmt = stmt.order_by(
            DramaTaskRecord.available_time.desc(),
            DramaTaskRecord.id.desc(),
        )
        records = self._session.execute(stmt).scalars().all()
        return [self._to_domain(r) for r in records]

    @staticmethod
    def _to_domain(record: DramaTaskRecord) -> DramaTask:
        """ORM → 领域模型."""
        return DramaTask(
            id=record.id,
            source_key=record.source_key or "",
            sheet_row=record.sheet_row,
            drama_name=record.drama_name,
            platform=record.platform,
            end_type=record.end_type or "NATIVE",
            available_time=record.available_time,
            owner=record.owner,
            status=record.status,
            link_set=_load_links(record.link_set_json),
            source_links=_load_links(record.source_links_json),
            link_status=record.link_status,
            current_stage=record.current_stage or "WAITING_AVAILABLE_TIME",
            target_stage=record.target_stage or "LINK_READY",
            delivery_drama_id=record.delivery_drama_id or "",
            promotion_configs=_load_links(record.promotion_configs_json),
            confirmed_drama_match=_load_confirmed_match(
                record.confirmed_drama_match_json
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def _load_links(raw: str | None) -> dict[str, str]:
    """读取任务链接快照；旧库或损坏值按空快照处理。"""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_confirmed_match(raw: str | None) -> ConfirmedDramaMatch | None:
    """读取人工确认；损坏或缺失值按未确认处理。"""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return ConfirmedDramaMatch.from_dict(data) if isinstance(data, dict) else None

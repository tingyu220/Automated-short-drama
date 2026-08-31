"""账户 CID 同日占用仓储。"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.errors.domain_error import ConflictError
from backend.domain.rules.account_sheet import AccountUsage
from backend.infrastructure.database.models.account import AccountUsageRecord


class SqlAlchemyAccountUsageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def used_cids(self, usage_day: date) -> set[str]:
        statement = select(AccountUsageRecord.cid).where(
            AccountUsageRecord.usage_day == usage_day
        )
        return set(self._session.execute(statement).scalars().all())

    def record_confirmed(self, usages: list[AccountUsage]) -> None:
        if not usages:
            return
        days = {usage.usage_day for usage in usages}
        if len(days) != 1:
            raise ConflictError("一次账户确认只能记录同一业务日期")
        day = next(iter(days))
        incoming = [usage.cid for usage in usages]
        if len(set(incoming)) != len(incoming):
            raise ConflictError("本次账户分配包含重复 CID")
        conflicts = self.used_cids(day).intersection(incoming)
        if conflicts:
            raise ConflictError(
                f"CID 当天已分配: {', '.join(sorted(conflicts))}"
            )
        self._session.add_all(
            [
                AccountUsageRecord(
                    id=str(uuid.uuid4()),
                    task_id=usage.task_id,
                    drama_name=usage.drama_name,
                    usage_day=usage.usage_day,
                    cid=usage.cid,
                    role=usage.role,
                    sheet_kind=usage.sheet_kind,
                    row_number=usage.row_number,
                )
                for usage in usages
            ]
        )
        self._session.flush()

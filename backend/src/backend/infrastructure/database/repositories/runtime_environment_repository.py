"""运行环境配置仓储。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.domain.runtime.environment import RuntimeEnvironment, RuntimeMode
from backend.infrastructure.database.models.runtime_environment import (
    RuntimeEnvironmentRecord,
)

_GLOBAL_ID = 1


class SqlAlchemyRuntimeEnvironmentRepository:
    """读写全局运行环境及 Worker 的已应用模式。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> RuntimeEnvironment:
        record = self._session.get(RuntimeEnvironmentRecord, _GLOBAL_ID)
        if record is None:
            return RuntimeEnvironment()
        return RuntimeEnvironment(
            desired_mode=record.desired_mode,
            worker_mode=record.worker_mode,
            configured=True,
            operator_match_group=record.operator_match_group,
        )

    def set_desired_mode(self, mode: str) -> RuntimeEnvironment:
        record = self._get_or_create()
        record.desired_mode = RuntimeMode.validate(mode)
        self._session.flush()
        return self.get()

    def mark_worker_mode(self, mode: str) -> RuntimeEnvironment:
        record = self._get_or_create()
        record.worker_mode = RuntimeMode.validate(mode)
        self._session.flush()
        return self.get()

    def set_operator_match_group(self, value: bool) -> RuntimeEnvironment:
        record = self._get_or_create()
        record.operator_match_group = value
        self._session.flush()
        return self.get()

    def _get_or_create(self) -> RuntimeEnvironmentRecord:
        record = self._session.get(RuntimeEnvironmentRecord, _GLOBAL_ID)
        if record is None:
            record = RuntimeEnvironmentRecord(id=_GLOBAL_ID)
            self._session.add(record)
            self._session.flush()
        return record

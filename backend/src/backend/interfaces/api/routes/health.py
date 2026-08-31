"""健康检查端点。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, text

from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.models.worker import WorkerLeaseRecord
from backend.infrastructure.database.repositories.runtime_environment_repository import (
    SqlAlchemyRuntimeEnvironmentRepository,
)

router = APIRouter()


@router.get("/healthz")
def healthz():
    """健康检查接口。

    始终返回 200；当数据库不可用时 status 降级为 "degraded"。
    """
    settings = Settings()
    database_status = "ok"
    worker_online = False
    active_worker_id = None
    environment = "MOCK"
    worker_environment = None
    environment_switching = False
    operator_match_group = False
    try:
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            lease = (
                session.execute(
                    select(WorkerLeaseRecord)
                    .where(
                        WorkerLeaseRecord.status == "RUNNING",
                        WorkerLeaseRecord.lease_until > now,
                    )
                    .limit(1)
                )
                .scalars()
                .first()
            )
            worker_online = lease is not None
            active_worker_id = lease.worker_id if lease is not None else None
            try:
                runtime_environment = (
                    SqlAlchemyRuntimeEnvironmentRepository(session).get()
                )
                environment = runtime_environment.desired_mode
                worker_environment = runtime_environment.worker_mode
                environment_switching = runtime_environment.switching
                operator_match_group = runtime_environment.operator_match_group
            except Exception:
                # 兼容尚未执行运行环境迁移的旧数据库。
                pass
        finally:
            session.close()
    except Exception:
        database_status = "error"

    return {
        "status": "degraded" if database_status == "error" else "ok",
        "app_name": settings.app_name,
        "version": "0.1.0",
        "allow_final_submit": settings.allow_final_submit,
        "worker_heartbeat": worker_online,
        "active_worker_id": active_worker_id,
        "database": database_status,
        "config": "ok",
        "environment": environment,
        "worker_environment": worker_environment,
        "environment_switching": environment_switching,
        "operator_match_group": operator_match_group,
    }

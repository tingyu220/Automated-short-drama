"""健康检查端点。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, text

from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.database.models.worker import WorkerLeaseRecord

router = APIRouter()


@router.get("/healthz")
def healthz():
    """健康检查接口。

    始终返回 200；当数据库不可用时 status 降级为 "degraded"。
    """
    settings = Settings()
    database_status = "ok"
    worker_online = False
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
        "database": database_status,
        "config": "ok",
    }

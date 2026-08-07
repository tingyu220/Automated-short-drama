"""记录 API 路由：台账、执行事件与执行产物查询。"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.infrastructure.database.repositories.execution_repository import (
    SqlAlchemyExecutionRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.repositories.ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from backend.infrastructure.database.session import get_session
from backend.infrastructure.config.settings import Settings
from backend.interfaces.api.schemas import (
    ExecutionArtifactView,
    ExecutionEventView,
    LedgerView,
)

router = APIRouter(tags=["records"])


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库会话依赖。"""
    with get_session() as session:
        yield session


@router.get("/records/ledgers", response_model=list[LedgerView])
def list_ledgers(
    task_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """列出交付台账，可按 task_id 过滤。"""
    ledger_repo = SqlAlchemyLedgerRepository(db)
    ledgers = (
        ledger_repo.list_by_task(task_id) if task_id else ledger_repo.list_all()
    )
    task_rows = {
        task.id: task.sheet_row
        for task in SqlAlchemyTaskRepository(db).list_by_filters()
    }
    views = []
    for ledger in ledgers:
        view = LedgerView.model_validate(ledger)
        view.sheet_row = task_rows.get(ledger.task_id)
        views.append(view)
    return views


@router.get("/records/events", response_model=list[ExecutionEventView])
def list_execution_events(
    task_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """列出执行事件，可按 task_id 过滤。"""
    events = SqlAlchemyExecutionRepository(db).list_events(task_id=task_id)
    return [ExecutionEventView.model_validate(event) for event in events]


@router.get("/records/artifacts", response_model=list[ExecutionArtifactView])
def list_execution_artifacts(
    task_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """列出执行产物，可按 task_id 过滤。"""
    artifacts = SqlAlchemyExecutionRepository(db).list_artifacts(task_id=task_id)
    return [ExecutionArtifactView.model_validate(artifact) for artifact in artifacts]


@router.get("/artifacts/{artifact_path:path}")
def get_artifact_file(artifact_path: str):
    """按相对 data 目录的路径返回执行产物文件，越界路径一律 404。"""
    data_dir = Settings().data_dir.resolve()
    candidate = Path(artifact_path)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (data_dir / candidate).resolve()
    )
    try:
        resolved.relative_to(data_dir)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail="产物路径不在数据目录内"
        ) from exc
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="产物文件不存在")
    return FileResponse(resolved)

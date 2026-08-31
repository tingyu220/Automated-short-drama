"""公用剧目读取与确认导入 API。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.application.services.drama_import_service import DramaImportService
from backend.bootstrap.adapters import build_drama_sheet_adapter
from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.repositories.drama_import_repository import (
    SqlAlchemyDramaImportRunRepository,
)
from backend.infrastructure.database.repositories.runtime_environment_repository import (
    SqlAlchemyRuntimeEnvironmentRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.interfaces.api.routes.tasks import get_db
from backend.interfaces.api.schemas import (
    DramaImportConfirmBody,
    DramaImportErrorView,
    DramaImportOperatorView,
    DramaImportPreviewBody,
    DramaImportPreviewView,
    DramaImportRowView,
    DramaImportRunView,
    ImportedDramaRecordView,
)
from backend.domain.imports.drama_import import list_import_operators

router = APIRouter(prefix="/drama-import", tags=["drama-import"])


@router.get("/operators", response_model=list[DramaImportOperatorView])
def list_operators():
    return [
        DramaImportOperatorView(name=item.name, group_prefix=item.group_prefix)
        for item in list_import_operators()
    ]


def get_drama_sheet():
    """仅构造双表适配器；线上写入只发生在 confirm。"""
    return build_drama_sheet_adapter(Settings())


def get_drama_import_service(
    db: Session = Depends(get_db),
    sheet=Depends(get_drama_sheet),
) -> DramaImportService:
    return DramaImportService(
        sheet,
        run_repository=SqlAlchemyDramaImportRunRepository(db),
    )


@router.post("/preview", response_model=DramaImportPreviewView)
def preview_import(
    body: DramaImportPreviewBody,
    service: DramaImportService = Depends(get_drama_import_service),
    db: Session = Depends(get_db),
):
    """读取公用表并保存只读预览。"""
    runtime_env = SqlAlchemyRuntimeEnvironmentRepository(db).get()
    preview = service.preview(
        body.business_date,
        operator_name=body.operator_name,
        match_group=runtime_env.operator_match_group,
    )
    return DramaImportPreviewView(
        preview_id=preview.preview_id,
        business_date=body.business_date,
        source_count=preview.source_count,
        new_count=preview.new_count,
        duplicate_count=preview.duplicate_count,
        invalid_count=preview.invalid_count,
        rows=[
            DramaImportRowView(
                source_row=row.source_row,
                drama_name=row.drama_name,
                platform=row.cells[7],
                available_time=row.cells[4],
                has_validated_links=row.has_validated_links,
            )
            for row in preview.rows
        ],
        errors=[
            DramaImportErrorView(source_row=error.source_row, message=error.message)
            for error in preview.errors
        ],
    )


@router.post("/confirm", response_model=DramaImportRunView)
def confirm_import(
    body: DramaImportConfirmBody,
    service: DramaImportService = Depends(get_drama_import_service),
):
    """确认后才向私有表顶部批量写入。"""
    service.confirm(body.preview_id)
    return _run_view(service, body.preview_id)


@router.get("/runs/{run_id}", response_model=DramaImportRunView)
def get_import_run(
    run_id: str,
    service: DramaImportService = Depends(get_drama_import_service),
):
    """查询导入状态，以便页面刷新后恢复。"""
    return _run_view(service, run_id)


@router.get("/records", response_model=list[ImportedDramaRecordView])
def list_imported_records(
    business_date: date = Query(...),
    service: DramaImportService = Depends(get_drama_import_service),
    db: Session = Depends(get_db),
):
    """列出已确认导入的当天剧目，并尽力关联本地任务。"""
    task_repository = SqlAlchemyTaskRepository(db)
    records: list[ImportedDramaRecordView] = []
    seen: set[str] = set()
    for run in service.list_confirmed_runs(business_date):
        for row in run.preview.rows:
            if row.source_key in seen:
                continue
            seen.add(row.source_key)
            task = task_repository.get_by_source_key(row.source_key)
            records.append(
                ImportedDramaRecordView(
                    source_key=row.source_key,
                    drama_name=row.drama_name,
                    platform=row.cells[7],
                    available_time=row.cells[4],
                    operator_name=_display_operator_name(row.cells[2]),
                    task_id=task.id if task else None,
                    task_status=task.status if task else None,
                )
            )
    return records


def _run_view(service: DramaImportService, run_id: str) -> DramaImportRunView:
    run = service.get_run(run_id)
    return DramaImportRunView(
        run_id=run.run_id,
        status=run.status,
        business_date=run.business_date,
        source_count=run.source_count,
        new_count=run.new_count,
        duplicate_count=run.duplicate_count,
        invalid_count=run.invalid_count,
        inserted_count=run.inserted_count,
        inserted_rows=list(run.inserted_rows),
        verified=run.verified,
        error_message=run.error_message,
    )


def _display_operator_name(group: str) -> str:
    """公有表 C 列以组别字母开头，候选表只展示实际投手姓名。"""
    normalized = group.strip()
    if len(normalized) > 1 and normalized[0].isascii() and normalized[0].isalpha():
        return normalized[1:]
    return normalized

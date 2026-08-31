"""公用剧目导入私有剧目表的用例编排。"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from backend.domain.errors.domain_error import ConflictError, NotFoundError
from backend.domain.imports.drama_import import (
    DramaImportPreview,
    PrivateDramaRow,
    PublicDramaRow,
    build_import_preview,
)
from backend.domain.imports.import_run import DramaImportRun, ImportRunStatus


class DramaSheetPort(Protocol):
    """导入用例所需的飞书表格能力。"""

    def read_public_rows(self, business_date: date) -> list[PublicDramaRow]: ...
    def read_private_rows(self) -> list[tuple[str, ...]]: ...
    def private_revision(self) -> int: ...
    def insert_private_rows(
        self, rows: list[PrivateDramaRow], *, expected_revision: int
    ) -> object: ...


class DramaImportRunPort(Protocol):
    """导入预览与确认结果的持久化边界。"""

    def add(self, run: DramaImportRun) -> DramaImportRun: ...
    def get(self, run_id: str) -> DramaImportRun | None: ...
    def list_completed_by_business_date(self, business_date: date) -> list[DramaImportRun]: ...
    def claim(self, run_id: str) -> DramaImportRun | None: ...
    def complete(
        self,
        run_id: str,
        *,
        inserted_count: int,
        inserted_rows: tuple[int, ...],
        verified: bool,
    ) -> DramaImportRun: ...
    def fail(self, run_id: str, message: str) -> None: ...


@dataclass(frozen=True)
class ImportPreviewResult:
    """供界面确认的导入预览。"""

    preview_id: str
    source_count: int
    new_count: int
    duplicate_count: int
    invalid_count: int
    rows: tuple[PrivateDramaRow, ...]
    errors: tuple[object, ...]


@dataclass(frozen=True)
class ImportRunResult:
    """已确认导入的结果快照。"""

    run_id: str
    inserted_count: int
    inserted_rows: tuple[int, ...]
    verified: bool


@dataclass(frozen=True)
class ImportRunView:
    """导入记录查询结果。"""

    run_id: str
    status: str
    business_date: date
    source_count: int
    new_count: int
    duplicate_count: int
    invalid_count: int
    inserted_count: int
    inserted_rows: tuple[int, ...]
    verified: bool
    error_message: str | None


@dataclass(frozen=True)
class _PendingPreview:
    preview: DramaImportPreview
    revision: int


class DramaImportService:
    """将公用表当天剧目以确认式写入私有表。"""

    def __init__(
        self,
        sheet: DramaSheetPort,
        *,
        run_repository: DramaImportRunPort | None = None,
        run_store: dict[str, _PendingPreview | ImportRunResult] | None = None,
    ) -> None:
        self._sheet = sheet
        self._run_repository = run_repository
        self._run_store = run_store if run_store is not None else {}
        self._lock = threading.Lock()

    def preview(
        self, business_date: date, *, operator_name: str = "田雨", match_group: bool = False
    ) -> ImportPreviewResult:
        """生成预览，只读两张表，不触发写操作。"""
        preview = build_import_preview(
            self._sheet.read_public_rows(business_date),
            self._sheet.read_private_rows(),
            business_date,
            operator_name=operator_name,
            match_group=match_group,
        )
        preview_id = str(uuid.uuid4())
        revision = self._sheet.private_revision()
        if self._run_repository is not None:
            self._run_repository.add(
                DramaImportRun(
                    id=preview_id,
                    preview=preview,
                    expected_revision=revision,
                )
            )
            return _to_preview_result(preview_id, preview)
        with self._lock:
            self._run_store[preview_id] = _PendingPreview(
                preview=preview,
                revision=revision,
            )
        return _to_preview_result(preview_id, preview)

    def confirm(self, preview_id: str) -> ImportRunResult:
        """确认后执行一次顶部插入；重复确认返回首次结果。"""
        if self._run_repository is not None:
            return self._confirm_persisted(preview_id)
        with self._lock:
            stored = self._run_store.get(preview_id)
            if isinstance(stored, ImportRunResult):
                return stored
            if stored is None:
                raise ValueError("导入预览不存在或已过期")
            pending = stored

            result = self._sheet.insert_private_rows(
                list(pending.preview.rows),
                expected_revision=pending.revision,
            )
            completed = ImportRunResult(
                run_id=preview_id,
                inserted_count=result.inserted_count,
                inserted_rows=tuple(result.inserted_rows),
                verified=result.verified,
            )
            self._run_store[preview_id] = completed
            return completed

    def get_run(self, run_id: str) -> ImportRunView:
        """查询本地导入日志，供刷新后的界面恢复进度。"""
        if self._run_repository is None:
            raise NotFoundError("导入记录尚未持久化")
        run = self._run_repository.get(run_id)
        if run is None:
            raise NotFoundError(f"DramaImportRun {run_id} not found")
        return _to_run_view(run)

    def list_confirmed_runs(self, business_date: date) -> list[DramaImportRun]:
        if self._run_repository is None:
            return []
        return self._run_repository.list_completed_by_business_date(business_date)

    def _confirm_persisted(self, preview_id: str) -> ImportRunResult:
        if self._run_repository is None:
            raise RuntimeError("run_repository 未初始化，无法确认导入")
        existing = self._run_repository.get(preview_id)
        if existing is None:
            raise NotFoundError(f"DramaImportRun {preview_id} not found")
        if existing.status == ImportRunStatus.COMPLETED:
            return _to_run_result(existing)

        claimed = self._run_repository.claim(preview_id)
        if claimed is None:
            latest = self._run_repository.get(preview_id)
            if latest is not None and latest.status == ImportRunStatus.COMPLETED:
                return _to_run_result(latest)
            raise ConflictError("该导入预览正在确认中，请稍后刷新结果")

        try:
            result = self._sheet.insert_private_rows(
                list(claimed.preview.rows),
                expected_revision=claimed.expected_revision,
            )
        except Exception as exc:
            self._run_repository.fail(preview_id, str(exc))
            raise
        completed = self._run_repository.complete(
            preview_id,
            inserted_count=result.inserted_count,
            inserted_rows=tuple(result.inserted_rows),
            verified=result.verified,
        )
        return _to_run_result(completed)


def _to_preview_result(
    preview_id: str, preview: DramaImportPreview
) -> ImportPreviewResult:
    return ImportPreviewResult(
        preview_id=preview_id,
        source_count=preview.source_count,
        new_count=preview.new_count,
        duplicate_count=preview.duplicate_count,
        invalid_count=preview.invalid_count,
        rows=preview.rows,
        errors=preview.errors,
    )


def _to_run_result(run: DramaImportRun) -> ImportRunResult:
    return ImportRunResult(
        run_id=run.id,
        inserted_count=run.inserted_count,
        inserted_rows=run.inserted_rows,
        verified=run.verified,
    )


def _to_run_view(run: DramaImportRun) -> ImportRunView:
    return ImportRunView(
        run_id=run.id,
        status=run.status,
        business_date=run.business_date,
        source_count=run.preview.source_count,
        new_count=run.preview.new_count,
        duplicate_count=run.preview.duplicate_count,
        invalid_count=run.preview.invalid_count,
        inserted_count=run.inserted_count,
        inserted_rows=run.inserted_rows,
        verified=run.verified,
        error_message=run.error_message,
    )

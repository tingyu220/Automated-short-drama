"""剧目导入运行记录的 SQLAlchemy 仓储。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.domain.imports.drama_import import (
    DramaImportPreview,
    ImportRowError,
    PrivateDramaRow,
)
from backend.domain.imports.import_run import DramaImportRun, ImportRunStatus
from backend.infrastructure.database.models.drama_import import DramaImportRunRecord


class SqlAlchemyDramaImportRunRepository:
    """预览在请求间持久化，并用条件更新抢占确认操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: DramaImportRun) -> DramaImportRun:
        self._session.add(
            DramaImportRunRecord(
                id=run.id,
                business_date=run.business_date,
                expected_revision=run.expected_revision,
                preview_json=_dump_preview(run.preview),
                status=run.status,
            )
        )
        self._session.flush()
        return run

    def get(self, run_id: str) -> DramaImportRun | None:
        record = self._session.get(DramaImportRunRecord, run_id)
        return self._to_domain(record) if record is not None else None

    def list_completed_by_business_date(self, business_date) -> list[DramaImportRun]:
        records = self._session.execute(
            select(DramaImportRunRecord)
            .where(
                DramaImportRunRecord.business_date == business_date,
                DramaImportRunRecord.status == ImportRunStatus.COMPLETED,
            )
            .order_by(DramaImportRunRecord.created_at.desc())
        ).scalars().all()
        return [self._to_domain(record) for record in records]

    def claim(self, run_id: str) -> DramaImportRun | None:
        claimed = self._session.execute(
            update(DramaImportRunRecord)
            .where(
                DramaImportRunRecord.id == run_id,
                DramaImportRunRecord.status == ImportRunStatus.PREVIEWED,
            )
            .values(status=ImportRunStatus.RUNNING, updated_at=datetime.now(timezone.utc))
        ).rowcount
        self._session.flush()
        return self.get(run_id) if claimed == 1 else None

    def complete(
        self,
        run_id: str,
        *,
        inserted_count: int,
        inserted_rows: tuple[int, ...],
        verified: bool,
    ) -> DramaImportRun:
        record = self._required_record(run_id)
        record.status = ImportRunStatus.COMPLETED
        record.inserted_count = inserted_count
        record.inserted_rows_json = json.dumps(inserted_rows)
        record.verified = verified
        record.error_message = None
        self._session.flush()
        return self._to_domain(record)

    def fail(self, run_id: str, message: str) -> None:
        record = self._required_record(run_id)
        record.status = ImportRunStatus.FAILED
        record.error_message = message
        self._session.flush()

    def _required_record(self, run_id: str) -> DramaImportRunRecord:
        record = self._session.get(DramaImportRunRecord, run_id)
        if record is None:
            raise ValueError(f"DramaImportRun {run_id} not found")
        return record

    @staticmethod
    def _to_domain(record: DramaImportRunRecord) -> DramaImportRun:
        return DramaImportRun(
            id=record.id,
            preview=_load_preview(record.business_date, record.preview_json),
            expected_revision=record.expected_revision,
            status=record.status,
            inserted_count=record.inserted_count,
            inserted_rows=tuple(json.loads(record.inserted_rows_json or "[]")),
            verified=record.verified,
            error_message=record.error_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def _dump_preview(preview: DramaImportPreview) -> str:
    return json.dumps(
        {
            "source_count": preview.source_count,
            "new_count": preview.new_count,
            "duplicate_count": preview.duplicate_count,
            "invalid_count": preview.invalid_count,
            "rows": [
                {
                    "source_row": row.source_row,
                    "source_key": row.source_key,
                    "cells": list(row.cells),
                    "has_validated_links": row.has_validated_links,
                    "fill_colors": list(row.fill_colors),
                }
                for row in preview.rows
            ],
            "errors": [
                {"source_row": error.source_row, "message": error.message}
                for error in preview.errors
            ],
            "operator_name": preview.operator_name,
        },
        ensure_ascii=False,
    )


def _load_preview(business_date, raw: str) -> DramaImportPreview:
    data = json.loads(raw)
    return DramaImportPreview(
        business_date=business_date,
        source_count=int(data["source_count"]),
        new_count=int(data["new_count"]),
        duplicate_count=int(data["duplicate_count"]),
        invalid_count=int(data["invalid_count"]),
        rows=tuple(
            PrivateDramaRow(
                source_row=int(row["source_row"]),
                source_key=str(row["source_key"]),
                cells=tuple(row["cells"]),
                has_validated_links=bool(row["has_validated_links"]),
                fill_colors=tuple(row.get("fill_colors") or ()),
            )
            for row in data["rows"]
        ),
        errors=tuple(
            ImportRowError(
                source_row=int(error["source_row"]), message=str(error["message"])
            )
            for error in data["errors"]
        ),
        operator_name=str(data.get("operator_name", "田雨")),
    )

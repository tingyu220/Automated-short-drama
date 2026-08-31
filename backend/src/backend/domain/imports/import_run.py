"""剧目导入运行记录领域模型。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from backend.domain.imports.drama_import import DramaImportPreview


class ImportRunStatus:
    """导入确认的可恢复状态。"""

    PREVIEWED = "PREVIEWED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class DramaImportRun:
    """一次预览及其确认写入结果。"""

    id: str
    preview: DramaImportPreview
    expected_revision: int
    status: str = ImportRunStatus.PREVIEWED
    inserted_count: int = 0
    inserted_rows: tuple[int, ...] = ()
    verified: bool = False
    error_message: str | None = None
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)

    @property
    def business_date(self) -> date:
        return self.preview.business_date

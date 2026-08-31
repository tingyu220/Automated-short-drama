"""剧目导入用例：预览只读，确认操作可恢复且幂等。"""
from __future__ import annotations

from datetime import date

import pytest

from backend.application.services.drama_import_service import DramaImportService
from backend.domain.imports.drama_import import PrivateDramaRow, PublicDramaRow


def _public_row() -> PublicDramaRow:
    cells = [""] * 28
    cells[4] = "2026/8/17 10:00"
    cells[5] = "今日新剧"
    cells[2] = "B田雨-林浩东"
    cells[10] = "番茄"
    return PublicDramaRow(row_number=4, cells=tuple(cells))


class FakeDramaSheet:
    def __init__(self) -> None:
        self.insert_calls = 0
        self.inserted_rows: list[PrivateDramaRow] = []

    def read_public_rows(self, business_date: date) -> list[PublicDramaRow]:
        assert business_date == date(2026, 8, 17)
        return [_public_row()]

    def read_private_rows(self) -> list[tuple[str, ...]]:
        return []

    def private_revision(self) -> int:
        return 18

    def insert_private_rows(
        self, rows: list[PrivateDramaRow], *, expected_revision: int
    ) -> object:
        assert expected_revision == 18
        self.insert_calls += 1
        self.inserted_rows.extend(rows)
        return type(
            "InsertResult",
            (),
            {"inserted_count": len(rows), "inserted_rows": (2,), "verified": True},
        )()


def test_preview_is_read_only_and_confirm_is_idempotent() -> None:
    """若删掉确认门槛或重复写入保护，测试必须失败。"""
    sheet = FakeDramaSheet()
    service = DramaImportService(sheet)

    preview = service.preview(date(2026, 8, 17))

    assert preview.new_count == 1
    assert preview.duplicate_count == 0
    assert sheet.insert_calls == 0

    first = service.confirm(preview.preview_id)
    repeated = service.confirm(preview.preview_id)

    assert first.run_id == repeated.run_id
    assert first.inserted_count == 1
    assert repeated.inserted_rows == (2,)
    assert sheet.insert_calls == 1
    assert [row.drama_name for row in sheet.inserted_rows] == ["今日新剧"]


def test_confirm_reuses_preview_saved_by_another_service_instance() -> None:
    """若预览仅存于 API 请求内存中，第二次请求将无法确认。"""
    sheet = FakeDramaSheet()
    run_store = {}
    preview_service = DramaImportService(sheet, run_store=run_store)
    preview = preview_service.preview(date(2026, 8, 17))

    result = DramaImportService(sheet, run_store=run_store).confirm(preview.preview_id)

    assert result.inserted_count == 1
    assert sheet.insert_calls == 1


def test_confirm_persisted_raises_runtime_error_without_repository() -> None:
    """_confirm_persisted 在 run_repository 为 None 时必须抛 RuntimeError，不依赖 assert。"""
    service = DramaImportService(FakeDramaSheet())
    with pytest.raises(RuntimeError, match="run_repository 未初始化"):
        service._confirm_persisted("any-id")


def test_match_group_false_excludes_same_group_different_name() -> None:
    """match_group=False 时，同组但名字不同的行不纳入预览。"""
    from backend.domain.imports.drama_import import build_import_preview

    own_row = PublicDramaRow(
        row_number=1,
        cells=tuple(_make_cells(group="B-田雨", time="2026/8/17 10:00")),
    )
    group_only_row = PublicDramaRow(
        row_number=2,
        cells=tuple(_make_cells(group="B-张朔", time="2026/8/17 10:00")),
    )
    preview = build_import_preview(
        [own_row, group_only_row],
        [],
        date(2026, 8, 17),
        operator_name="田雨",
        match_group=False,
    )
    assert preview.source_count == 1
    assert preview.rows[0].drama_name == "今日新剧"


def test_match_group_true_includes_same_group() -> None:
    """match_group=True 时，同组但名字不同的行也纳入预览。"""
    from backend.domain.imports.drama_import import build_import_preview

    own_row = PublicDramaRow(
        row_number=1,
        cells=tuple(_make_cells(group="B-田雨", time="2026/8/17 10:00")),
    )
    group_only_row = PublicDramaRow(
        row_number=2,
        cells=tuple(_make_cells(group="B-张朔", time="2026/8/17 10:00", name="同组剧目")),
    )
    preview = build_import_preview(
        [own_row, group_only_row],
        [],
        date(2026, 8, 17),
        operator_name="田雨",
        match_group=True,
    )
    assert preview.source_count == 2


def _make_cells(*, group: str, time: str, name: str = "今日新剧") -> list[str]:
    cells = [""] * 28
    cells[2] = group
    cells[4] = time
    cells[5] = name
    cells[10] = "番茄"
    return cells

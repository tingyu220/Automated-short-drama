from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import pytest

from backend.domain.errors.domain_error import ConflictError, ExternalAdapterError
from backend.domain.imports.drama_import import PrivateDramaRow
import backend.platforms.feishu.drama_sheet_adapter as drama_sheet_module
from backend.platforms.feishu.drama_sheet_adapter import DramaSheetAdapter


PUBLIC_URL = "https://example.feishu.cn/wiki/public?sheet=public-id"
PRIVATE_URL = "https://example.feishu.cn/wiki/private?sheet=private-id"


@dataclass
class Completed:
    stdout: str
    returncode: int = 0
    stderr: str = ""


class SequenceRunner:
    def __init__(self, outputs: list[dict]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command: list[str], **kwargs) -> Completed:
        self.calls.append((list(command), dict(kwargs)))
        return Completed(json.dumps(self.outputs.pop(0), ensure_ascii=False))


def _envelope(**data) -> dict:
    return {"ok": True, "data": data}


def _private_row(name: str = "今日剧") -> PrivateDramaRow:
    cells = (
        "测试组B",
        "新增",
        "B田雨-林浩东",
        "",
        "2026/8/17 10:00",
        name,
        "",
        "番茄",
        "漫剧",
        "",
        "",
        "",
        "",
        "有人未上",
    )
    return PrivateDramaRow(4, f"key-{name}", cells)


def test_windows_real_runner_uses_node_script_to_preserve_url_query(monkeypatch):
    """URL 含 & 时不能经 Windows cmd 批处理入口解析。"""
    runner = SequenceRunner([_envelope(revision=9)])
    monkeypatch.setattr(drama_sheet_module.subprocess, "run", runner)
    monkeypatch.setattr(drama_sheet_module.sys, "platform", "win32")
    monkeypatch.setattr(
        drama_sheet_module.shutil,
        "which",
        lambda name: (
            r"C:\\Node\\node.exe"
            if name == "node.exe"
            else r"C:\\Users\\tingyu\\AppData\\Roaming\\npm\\lark-cli.cmd"
            if name == "lark-cli.cmd"
            else None
        ),
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    assert adapter.private_revision() == 9
    assert runner.calls[0][0][0].endswith("node.exe")
    assert runner.calls[0][0][1].endswith("scripts\\run.js")
    assert runner.calls[0][0][2] == "sheets"
    assert runner.calls[0][1]["encoding"] == "utf-8"


def test_read_public_rows_scans_date_column_then_fetches_only_matching_rows():
    public_csv = (
        "[row=2]2026/8/16 23:59,昨日剧\n"
        "[row=3]2026/8/17 16:00,剧B\n"
        "[row=4]2026/8/17 0:10,剧A\n"
    )
    full_csv = (
        "[row=3] ,新增,B田雨-林浩东,,2026/8/17 16:00,剧B,,,,,番茄,,,,,,,,,,,,,,,,,有人未上\n"
        "[row=4] ,新增,B田雨-林浩东,,2026/8/17 0:10,剧A,,,,,番茄,,,,,,,,,,,,,,,,,有人未上"
    )
    runner = SequenceRunner(
        [
            _envelope(sheets=[{"sheet_id": "public-id", "row_count": 4}]),
            _envelope(annotated_csv=public_csv),
            _envelope(annotated_csv=full_csv),
            _envelope(
                ranges=[
                    {
                        "row_indices": [3, 4],
                        "cells": [
                            [{"cell_styles": {"background_color": "#fff258"}}] * 28,
                            [{"cell_styles": {"background_color": "#fdddef"}}] * 28,
                        ],
                    }
                ]
            ),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    rows = adapter.read_public_rows(date(2026, 8, 17))

    assert [row.row_number for row in rows] == [3, 4]
    assert [row.cells[4] for row in rows] == [
        "2026/8/17 16:00",
        "2026/8/17 0:10",
    ]
    assert "E1:F4" in runner.calls[1][0]
    assert "A3:AB4" in runner.calls[2][0]
    assert PUBLIC_URL in runner.calls[2][0]
    assert "A3:AB4" in runner.calls[3][0]
    assert rows[0].fill_colors[0] == "#fff258"


def test_read_private_rows_reads_actual_workbook_row_count():
    runner = SequenceRunner(
        [
            _envelope(sheets=[{"sheet_id": "private-id", "row_count": 4}]),
            _envelope(
                annotated_csv=(
                    "[row=1]A,B,C,D,E,F,G,H,I,J,K,L,M,N\n"
                    "[row=2],,,,2026/8/17 10:00,今日剧,,番茄,,,,,,有人未上\n"
                    "[row=3],,,,,,,,,,,,,"
                )
            ),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    rows = adapter.read_private_rows()

    assert len(rows) == 2
    assert rows[0][4:8] == ("2026/8/17 10:00", "今日剧", "", "番茄")
    assert "A1:N4" in runner.calls[1][0]
    assert PRIVATE_URL in runner.calls[1][0]


def test_insert_private_rows_batches_top_insert_write_and_row_height_then_reads_back():
    first = _private_row("剧A")
    second = _private_row("剧B")
    readback = "\n".join(
        [
            "[row=2]" + ",".join(first.cells),
            "[row=3]" + ",".join(second.cells),
        ]
    )
    runner = SequenceRunner(
        [
            _envelope(revision=120, sheets=[]),
            _envelope(row_heights=[{"rows": "1:8", "height": 80}]),
            _envelope(revision=121),
            _envelope(status="success"),
            _envelope(annotated_csv=readback),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    result = adapter.insert_private_rows([first, second], expected_revision=120)

    batch_command, batch_kwargs = runner.calls[2]
    operations = json.loads(batch_kwargs["input"])
    assert batch_command[:3] == ["lark-cli", "sheets", "+batch-update"]
    assert "--yes" in batch_command
    assert operations[0] == {
        "shortcut": "+dim-insert",
        "input": {
            "sheet_id": "private-id",
            "position": "2",
            "count": 2,
            "inherit_style": "after",
        },
    }
    assert operations[1]["shortcut"] == "+cells-set"
    assert operations[1]["input"]["range"] == "A2:N3"
    assert operations[2]["input"] == {
        "sheet_id": "private-id",
        "range": "2:3",
        "height": 80,
    }
    assert result.inserted_count == 2
    assert result.inserted_rows == (2, 3)
    assert result.verified is True


def test_insert_private_rows_writes_iaa_validation_as_formula_linked_to_private_owner_column():
    row = _private_row()
    readback = "[row=2]" + ",".join(row.cells)
    runner = SequenceRunner(
        [
            _envelope(revision=120, sheets=[]),
            _envelope(row_heights=[{"rows": "1:8", "height": 80}]),
            _envelope(revision=121),
            _envelope(status="success"),
            _envelope(annotated_csv=readback),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    adapter.insert_private_rows([row], expected_revision=120)

    operations = json.loads(runner.calls[2][1]["input"])
    written_n_cell = operations[1]["input"]["cells"][0][13]
    assert written_n_cell == {
        "formula": '=IF(COUNT(M2:M2)=0,"有人未上","OK")'
    }


def test_insert_private_rows_copies_public_background_colors_to_private_cells():
    source = _private_row()
    row = PrivateDramaRow(
        source.source_row,
        source.source_key,
        source.cells,
        fill_colors=("#fdddef",) + (None,) * 12 + ("#d9f3fd",),
    )
    runner = SequenceRunner(
        [
            _envelope(revision=120, sheets=[]),
            _envelope(row_heights=[{"rows": "1:8", "height": 80}]),
            _envelope(revision=121),
            _envelope(status="success"),
            _envelope(annotated_csv="[row=2]" + ",".join(row.cells)),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    adapter.insert_private_rows([row], expected_revision=120)

    cells = json.loads(runner.calls[2][1]["input"])[1]["input"]["cells"][0]
    assert cells[0]["cell_styles"] == {"background_color": "#fdddef"}
    assert cells[13]["cell_styles"] == {"background_color": "#d9f3fd"}


def test_insert_private_rows_accepts_iaa_status_recalculated_from_private_owner_value():
    source = _private_row()
    source_cells = list(source.cells)
    source_cells[12] = "1"
    row = PrivateDramaRow(source.source_row, source.source_key, tuple(source_cells))
    actual_cells = list(row.cells)
    actual_cells[13] = "OK"
    runner = SequenceRunner(
        [
            _envelope(revision=120, sheets=[]),
            _envelope(row_heights=[{"rows": "1:8", "height": 80}]),
            _envelope(revision=121),
            _envelope(status="success"),
            _envelope(annotated_csv="[row=2]" + ",".join(actual_cells)),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    result = adapter.insert_private_rows([row], expected_revision=120)

    assert result.verified is True


def test_insert_private_rows_rejects_stale_preview_revision_without_writing():
    runner = SequenceRunner(
        [
            _envelope(revision=121, sheets=[]),
            _envelope(annotated_csv="[row=2]错误行,,,,,,,,,,,,,"),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    with pytest.raises(ConflictError, match="表格已发生变化"):
        adapter.insert_private_rows([_private_row()], expected_revision=120)

    assert len(runner.calls) == 2


def test_insert_private_rows_recovers_when_rows_were_written_before_status_persisted():
    row = _private_row()
    runner = SequenceRunner(
        [
            _envelope(revision=121, sheets=[]),
            _envelope(annotated_csv="[row=2] " + ",".join(row.cells)),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    result = adapter.insert_private_rows([row], expected_revision=120)

    assert result == drama_sheet_module.InsertResult(1, (2,), True)
    assert len(runner.calls) == 2


def test_insert_private_rows_raises_when_readback_does_not_match():
    runner = SequenceRunner(
        [
            _envelope(revision=120, sheets=[]),
            _envelope(row_heights=[{"rows": "2:2", "height": 80}]),
            _envelope(revision=121),
            _envelope(status="success"),
            _envelope(
                annotated_csv=(
                    "[row=2],,,,2026/8/17 10:00,错误剧名,,番茄,,,,,,有人未上"
                )
            ),
        ]
    )
    adapter = DramaSheetAdapter(
        PUBLIC_URL,
        "public-id",
        PRIVATE_URL,
        "private-id",
        runner=runner,
    )

    with pytest.raises(ExternalAdapterError, match="回读校验失败"):
        adapter.insert_private_rows([_private_row()], expected_revision=120)

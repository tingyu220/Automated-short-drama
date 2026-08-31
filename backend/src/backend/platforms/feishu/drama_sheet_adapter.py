"""公用剧目表与私有剧目表之间的导入适配器。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from itertools import groupby
from pathlib import Path
from typing import Callable

from backend.domain.errors.domain_error import ConflictError, ExternalAdapterError
from backend.domain.imports.drama_import import (
    PrivateDramaRow,
    PublicDramaRow,
    is_business_day_value,
)
from backend.platforms.feishu.sheet_parser import parse_annotated_rows


_PUBLIC_SCAN_CHUNK = 1000


@dataclass(frozen=True)
class InsertResult:
    inserted_count: int
    inserted_rows: tuple[int, ...]
    verified: bool


class DramaSheetAdapter:
    def __init__(
        self,
        public_url: str,
        public_sheet_id: str,
        private_url: str,
        private_sheet_id: str,
        *,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self._public_url = public_url
        self._public_sheet_id = public_sheet_id
        self._private_url = private_url
        self._private_sheet_id = private_sheet_id
        self._runner = runner

    def read_public_rows(self, day: date) -> list[PublicDramaRow]:
        row_count = self._sheet_row_count(self._public_url, self._public_sheet_id)
        matches: list[int] = []
        for start in range(1, row_count + 1, _PUBLIC_SCAN_CHUNK):
            end = min(start + _PUBLIC_SCAN_CHUNK - 1, row_count)
            result = self._read_csv(
                self._public_url,
                self._public_sheet_id,
                f"E{start}:F{end}",
            )
            for row_number, cells in parse_annotated_rows(result):
                raw_time = cells[0] if cells else ""
                if is_business_day_value(raw_time, day):
                    matches.append(row_number)

        rows: list[PublicDramaRow] = []
        for start, end in _contiguous_ranges(matches):
            result = self._read_csv(
                self._public_url,
                self._public_sheet_id,
                f"A{start}:AB{end}",
            )
            fill_colors = self._read_public_fill_colors(f"A{start}:AB{end}")
            rows.extend(
                PublicDramaRow(
                    row_number,
                    tuple([*cells, *([""] * 28)][:28]),
                    fill_colors.get(row_number, ()),
                )
                for row_number, cells in parse_annotated_rows(result)
            )
        return sorted(rows, key=lambda row: row.row_number)

    def read_private_rows(self) -> list[tuple[str, ...]]:
        row_count = self._sheet_row_count(self._private_url, self._private_sheet_id)
        result = self._read_csv(
            self._private_url,
            self._private_sheet_id,
            f"A1:N{row_count}",
        )
        return [
            tuple([*cells, *([""] * 14)][:14])
            for row_number, cells in parse_annotated_rows(result)
            if row_number > 1
        ]

    def private_revision(self) -> int:
        return self._workbook_info(self._private_url).get("revision", 0)

    def insert_private_rows(
        self,
        rows: list[PrivateDramaRow],
        *,
        expected_revision: int,
    ) -> InsertResult:
        if not rows:
            return InsertResult(0, (), True)
        current_revision = self.private_revision()
        if current_revision != expected_revision:
            end_row = len(rows) + 1
            readback = self._read_csv(
                self._private_url,
                self._private_sheet_id,
                f"A2:N{end_row}",
            )
            actual = [
                tuple([*cells, *([""] * 14)][:14])
                for _, cells in parse_annotated_rows(readback)
            ]
            expected = [_expected_private_readback(row) for row in rows]
            if actual == expected:
                return InsertResult(
                    inserted_count=len(rows),
                    inserted_rows=tuple(range(2, end_row + 1)),
                    verified=True,
                )
            raise ConflictError(
                "私有剧目表格已发生变化，请重新预览后再导入",
                details={
                    "expected_revision": expected_revision,
                    "current_revision": current_revision,
                },
            )

        row_height = self._private_row_height(2)
        end_row = len(rows) + 1
        operations = [
            {
                "shortcut": "+dim-insert",
                "input": {
                    "sheet_id": self._private_sheet_id,
                    "position": "2",
                    "count": len(rows),
                    "inherit_style": "after",
                },
            },
            {
                "shortcut": "+cells-set",
                "input": {
                    "sheet_id": self._private_sheet_id,
                    "range": f"A2:N{end_row}",
                    "cells": [
                        _private_row_cells_for_write(row, target_row)
                        for target_row, row in enumerate(rows, start=2)
                    ],
                },
            },
            {
                "shortcut": "+rows-resize",
                "input": {
                    "sheet_id": self._private_sheet_id,
                    "range": f"2:{end_row}",
                    "height": row_height,
                },
            },
        ]
        command = [
            "lark-cli",
            "sheets",
            "+batch-update",
            "--url",
            self._private_url,
            "--operations",
            "-",
            "--yes",
            "--as",
            "user",
            "--format",
            "json",
        ]
        self._run(command, input_text=json.dumps(operations, ensure_ascii=False))
        self._verify_private_formulas(f"N2:N{end_row}")

        readback = self._read_csv(
            self._private_url,
            self._private_sheet_id,
            f"A2:N{end_row}",
        )
        actual = [
            tuple([*cells, *([""] * 14)][:14])
            for _, cells in parse_annotated_rows(readback)
        ]
        expected = [_expected_private_readback(row) for row in rows]
        if actual != expected:
            raise ExternalAdapterError(
                "私有剧目表回读校验失败",
                details={"expected_rows": len(expected), "actual_rows": len(actual)},
            )
        return InsertResult(
            inserted_count=len(rows),
            inserted_rows=tuple(range(2, end_row + 1)),
            verified=True,
        )

    def _sheet_row_count(self, url: str, sheet_id: str) -> int:
        sheets = self._workbook_info(url).get("sheets") or []
        for sheet in sheets:
            if sheet.get("sheet_id") == sheet_id:
                return max(1, int(sheet.get("row_count") or 1))
        raise ExternalAdapterError(f"飞书工作簿中找不到 Sheet: {sheet_id}")

    def _workbook_info(self, url: str) -> dict:
        return self._run(
            [
                "lark-cli",
                "sheets",
                "+workbook-info",
                "--url",
                url,
                "--as",
                "user",
                "--format",
                "json",
            ]
        )

    def _read_csv(self, url: str, sheet_id: str, cell_range: str) -> str:
        data = self._run(
            [
                "lark-cli",
                "sheets",
                "+csv-get",
                "--url",
                url,
                "--sheet-id",
                sheet_id,
                "--range",
                cell_range,
                "--max-chars",
                "5000000",
                "--as",
                "user",
                "--format",
                "json",
            ]
        )
        annotated = data.get("annotated_csv")
        if not isinstance(annotated, str):
            raise ExternalAdapterError("飞书读取结果缺少 annotated_csv")
        if data.get("has_more"):
            raise ExternalAdapterError(f"飞书读取范围被截断: {cell_range}")
        return annotated

    def _private_row_height(self, row_number: int) -> int:
        data = self._run(
            [
                "lark-cli",
                "sheets",
                "+sheet-info",
                "--url",
                self._private_url,
                "--sheet-id",
                self._private_sheet_id,
                "--include",
                "row_heights",
                "--as",
                "user",
                "--format",
                "json",
            ]
        )
        for item in data.get("row_heights") or []:
            if _range_contains(item.get("rows", ""), row_number):
                return int(item.get("height") or 80)
        return 80

    def _read_public_fill_colors(
        self, cell_range: str
    ) -> dict[int, tuple[str | None, ...]]:
        data = self._run(
            [
                "lark-cli",
                "sheets",
                "+cells-get",
                "--url",
                self._public_url,
                "--sheet-id",
                self._public_sheet_id,
                "--range",
                cell_range,
                "--include",
                "style",
                "--as",
                "user",
                "--format",
                "json",
            ]
        )
        colors: dict[int, tuple[str | None, ...]] = {}
        for result_range in data.get("ranges") or []:
            row_indices = result_range.get("row_indices") or []
            rows = result_range.get("cells") or []
            for row_number, cells in zip(row_indices, rows):
                colors[int(row_number)] = tuple(
                    _background_color(cell) for cell in cells
                )
        return colors

    def _verify_private_formulas(self, cell_range: str) -> None:
        data = self._run(
            [
                "lark-cli",
                "sheets",
                "+formula-verify",
                "--url",
                self._private_url,
                "--sheet-id",
                self._private_sheet_id,
                "--range",
                cell_range,
                "--as",
                "user",
                "--format",
                "json",
            ]
        )
        if data.get("status") != "success":
            raise ExternalAdapterError(
                "私有剧目表 IAA 校验公式校验失败",
                details={"range": cell_range, "result": data},
            )

    def _run(self, command: list[str], input_text: str | None = None) -> dict:
        command = self._resolve_command(command)
        kwargs = {
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "capture_output": True,
        }
        if input_text is not None:
            kwargs["input"] = input_text
        try:
            completed = self._runner(command, **kwargs)
        except Exception as exc:
            raise ExternalAdapterError(f"lark-cli 执行失败: {exc}") from exc
        if getattr(completed, "returncode", 0) != 0:
            raise ExternalAdapterError(
                f"lark-cli 命令失败: {getattr(completed, 'stderr', '')}"
            )
        try:
            envelope = json.loads(getattr(completed, "stdout", "") or "{}")
        except json.JSONDecodeError as exc:
            raise ExternalAdapterError("lark-cli 输出不是合法 JSON") from exc
        if envelope.get("ok") is not True:
            error = envelope.get("error") or {}
            raise ExternalAdapterError(error.get("message") or "lark-cli 调用失败")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise ExternalAdapterError("lark-cli 响应缺少 data")
        return data

    def _resolve_command(self, command: list[str]) -> list[str]:
        """Windows 真实环境显式调用 npm 生成的 .cmd 包装器。"""
        if (
            sys.platform != "win32"
            or self._runner is not subprocess.run
            or not command
            or command[0] != "lark-cli"
        ):
            return command
        wrapper = shutil.which("lark-cli.cmd")
        if wrapper is None:
            return ["lark-cli.cmd", *command[1:]]
        script = Path(wrapper).parent / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
        return [shutil.which("node.exe") or "node.exe", str(script), *command[1:]]


def _contiguous_ranges(rows: list[int]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for _, group in groupby(enumerate(sorted(set(rows))), lambda item: item[1] - item[0]):
        values = [row for _, row in group]
        ranges.append((values[0], values[-1]))
    return ranges


def _range_contains(raw_range: str, row_number: int) -> bool:
    try:
        start, _, end = raw_range.partition(":")
        return int(start) <= row_number <= int(end or start)
    except ValueError:
        return False


def _private_row_cells_for_write(
    row: PrivateDramaRow, target_row: int
) -> list[dict]:
    """N 列按私有表唯一的人员完成列 M 生成联动 IAA 校验。"""
    colors = [*row.fill_colors, *([None] * 14)][:14]
    cells = [_cell_for_write(value, colors[index]) for index, value in enumerate(row.cells[:13])]
    validation_cell = {
        "formula": (
            f'=IF(COUNT(M{target_row}:M{target_row})=0,"有人未上","OK")'
        )
    }
    if colors[13]:
        validation_cell["cell_styles"] = {"background_color": colors[13]}
    cells.append(validation_cell)
    return cells


def _cell_for_write(value: str, fill_color: str | None) -> dict:
    cell: dict = {"value": value}
    if fill_color:
        cell["cell_styles"] = {"background_color": fill_color}
    return cell


def _background_color(cell: object) -> str | None:
    if not isinstance(cell, dict):
        return None
    styles = cell.get("cell_styles")
    if not isinstance(styles, dict):
        return None
    color = styles.get("background_color")
    return str(color) if color else None


def _expected_private_readback(row: PrivateDramaRow) -> tuple[str, ...]:
    """N 列是私有表公式结果，不能与公有表 AB 列的来源快照比较。"""
    cells = list(row.cells)
    cells[13] = "OK" if _is_number(cells[12]) else "有人未上"
    return tuple(cells)


def _is_number(value: str) -> bool:
    try:
        float(value.strip())
        return True
    except ValueError:
        return False

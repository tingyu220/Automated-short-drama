"""飞书剧目表 annotated CSV 解析器."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from backend.domain.common.timezones import SHANGHAI_TZ, UTC
from backend.domain.tasks.drama_task import DramaTask
from backend.domain.tasks.source_key import build_task_source_key


_ROW_PREFIX_RE = re.compile(r"^\[row=(\d+)\]")
_TIME_FORMATS = ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")

# 列号按 A1:N200 固定映射：E=5、F=6、H=8、N=14。
_TIME_COLUMN = 4
_DRAMA_NAME_COLUMN = 5
_PLATFORM_COLUMN = 7
_STATUS_COLUMN = 13
_LINK_COLUMNS = {"IAA": 9, "9.9": 10, "2.9": 11}
_PLATFORM_NAMES = {"番茄": "TOMATO", "剧变": "JUBIAN"}


def parse_task_rows(annotated_csv: str) -> list[DramaTask]:
    """解析 `[row=N]` 前缀行，返回 DramaTask 列表；坏行跳过。"""
    tasks: list[DramaTask] = []
    for row_number, cells in parse_annotated_rows(annotated_csv):
        task = _to_task(row_number, cells)
        if task is not None:
            tasks.append(task)
    return tasks


def parse_annotated_rows(annotated_csv: str) -> list[tuple[int, list[str]]]:
    """把 annotated CSV 按 `[row=N]` 解析为 (行号, 单元格列表)。"""
    rows: list[tuple[int, list[str]]] = []
    current_row: int | None = None
    record_lines: list[str] = []
    in_quotes = False

    def flush() -> None:
        nonlocal current_row, record_lines, in_quotes
        if current_row is None:
            return
        rows.append((current_row, _parse_record("\n".join(record_lines))))
        current_row = None
        record_lines = []
        in_quotes = False

    for line in annotated_csv.splitlines():
        match = _ROW_PREFIX_RE.match(line)
        if match is not None and not in_quotes:
            flush()
            current_row = int(match.group(1))
            record = line[match.end() :]
            # lark-cli 在 [row=N] 后附带一个标记分隔空格，不属于 A 列值。
            record_lines = [record[1:] if record.startswith(" ") else record]
            in_quotes = _quote_state(record_lines[0], False)
            continue
        if current_row is not None:
            record_lines.append(line)
            in_quotes = _quote_state(line, in_quotes)
            if not in_quotes:
                flush()
    flush()
    return rows


def _parse_record(record_text: str) -> list[str]:
    return next(csv.reader(io.StringIO(record_text)), [])


def _quote_state(line: str, in_quotes: bool) -> bool:
    """按 RFC 4180 统计一行引号状态（双引号转义不切换）。"""
    index = 0
    while index < len(line):
        if line[index] == '"':
            if index + 1 < len(line) and line[index + 1] == '"':
                index += 2
                continue
            in_quotes = not in_quotes
        index += 1
    return in_quotes


def _to_task(row_number: int, cells: list[str]) -> DramaTask | None:
    if len(cells) < _STATUS_COLUMN + 1:
        return None
    available_time = _parse_time(cells[_TIME_COLUMN])
    drama_name = cells[_DRAMA_NAME_COLUMN].strip()
    raw_platform = cells[_PLATFORM_COLUMN].strip()
    platform = _PLATFORM_NAMES.get(raw_platform, raw_platform)
    if available_time is None or not drama_name or not platform:
        return None
    source_links = {
        link_type: cells[index].strip()
        for link_type, index in _LINK_COLUMNS.items()
        if cells[index].strip()
    }
    is_validated = cells[_STATUS_COLUMN].strip().upper() == "OK" and bool(source_links)
    return DramaTask(
        id=str(row_number),
        source_key=build_task_source_key(drama_name, platform, cells[_TIME_COLUMN]),
        drama_name=drama_name,
        platform=platform,
        available_time=available_time,
        sheet_row=row_number,
        source_links=source_links,
        link_set=dict(source_links) if is_validated else {},
        link_status="VALIDATED" if is_validated else "NOT_STARTED",
    )


def _parse_time(raw: str) -> datetime | None:
    text = raw.strip()
    for fmt in _TIME_FORMATS:
        try:
            naive = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=SHANGHAI_TZ).astimezone(UTC)
    return None

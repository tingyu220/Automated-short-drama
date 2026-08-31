"""公用剧目表到私有剧目表的纯数据转换。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from backend.domain.tasks.source_key import build_task_source_key


@dataclass(frozen=True)
class PublicDramaRow:
    row_number: int
    cells: tuple[str, ...]
    fill_colors: tuple[str | None, ...] = ()


@dataclass(frozen=True)
class PrivateDramaRow:
    source_row: int
    source_key: str
    cells: tuple[str, ...]
    has_validated_links: bool = False
    fill_colors: tuple[str | None, ...] = ()

    @property
    def drama_name(self) -> str:
        return self.cells[5]


@dataclass(frozen=True)
class ImportRowError:
    source_row: int
    message: str


@dataclass(frozen=True)
class DramaImportPreview:
    business_date: date
    source_count: int
    new_count: int
    duplicate_count: int
    invalid_count: int
    rows: tuple[PrivateDramaRow, ...]
    errors: tuple[ImportRowError, ...]
    operator_name: str = "田雨"


@dataclass(frozen=True)
class ImportOperator:
    """人员导入范围及其在公有表的完成列。"""

    name: str
    group_prefix: str
    completion_column: int


_IMPORT_OPERATORS = (
    ImportOperator("赖亚健", "A", 15),
    ImportOperator("韩亚栋", "A", 16),
    ImportOperator("高有闯", "A", 17),
    ImportOperator("史浩镔", "A", 18),
    ImportOperator("陈冠鑫", "B", 19),
    ImportOperator("施凯波", "B", 20),
    ImportOperator("田雨", "B", 21),
    ImportOperator("张朔", "B", 22),
    ImportOperator("刘婧雯", "C", 23),
    ImportOperator("甘心远", "C", 24),
    ImportOperator("林浩东", "C", 25),
    ImportOperator("张子豪", "C", 26),
)
_OPERATORS_BY_NAME = {operator.name: operator for operator in _IMPORT_OPERATORS}


def list_import_operators() -> tuple[ImportOperator, ...]:
    return _IMPORT_OPERATORS


def resolve_import_operator(name: str) -> ImportOperator:
    operator = _OPERATORS_BY_NAME.get(name.strip())
    if operator is None:
        raise ValueError(f"不支持的导入人员: {name}")
    return operator


def map_public_row(
    row: PublicDramaRow, *, completion_column: int = 21
) -> PrivateDramaRow:
    cells = [*row.cells, *([""] * 28)][:28]
    drama_name = cells[5].strip()
    if not drama_name:
        raise ValueError("剧名不能为空")
    if not cells[4].strip():
        raise ValueError("上线时间不能为空")
    if not cells[10].strip():
        raise ValueError("平台不能为空")

    mapped = tuple(
        cells[index]
        for index in (*_PUBLIC_TO_PRIVATE_COLUMNS, completion_column, 27)
    )
    source_colors = [*row.fill_colors, *([None] * 28)][:28]
    mapped_colors = tuple(
        source_colors[index]
        for index in (*_PUBLIC_TO_PRIVATE_COLUMNS, completion_column, 27)
    )
    mapped = (*mapped[:5], drama_name, *mapped[6:])
    source_key = _identity_key(mapped[5], mapped[7], mapped[4])
    return PrivateDramaRow(
        source_row=row.row_number,
        source_key=source_key,
        cells=mapped,
        has_validated_links=(
            mapped[13].strip().upper() == "OK"
            and any(value.strip() for value in mapped[9:12])
        ),
        fill_colors=mapped_colors,
    )


def build_import_preview(
    public_rows: list[PublicDramaRow],
    private_rows: list[tuple[str, ...]],
    business_day: date,
    *,
    operator_name: str = "田雨",
    match_group: bool = False,
) -> DramaImportPreview:
    operator = resolve_import_operator(operator_name)
    existing_keys = {_private_identity(raw) for raw in private_rows}
    existing_keys.discard("")
    rows: list[PrivateDramaRow] = []
    errors: list[ImportRowError] = []
    duplicates = 0
    source_count = 0

    for source in public_rows:
        raw_time = source.cells[4] if len(source.cells) > 4 else ""
        if not is_business_day_value(raw_time, business_day) or not _is_operator_row(
            source, operator, match_group=match_group
        ):
            continue
        source_count += 1
        try:
            mapped = map_public_row(
                source, completion_column=operator.completion_column
            )
        except ValueError as exc:
            errors.append(ImportRowError(source.row_number, str(exc)))
            continue
        if mapped.source_key in existing_keys:
            duplicates += 1
            continue
        existing_keys.add(mapped.source_key)
        rows.append(mapped)

    return DramaImportPreview(
        business_date=business_day,
        source_count=source_count,
        new_count=len(rows),
        duplicate_count=duplicates,
        invalid_count=len(errors),
        rows=tuple(rows),
        errors=tuple(errors),
        operator_name=operator.name,
    )


_PUBLIC_TO_PRIVATE_COLUMNS = (0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14)
_DATE_PREFIX_RE = re.compile(r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s|$)")


def is_business_day_value(raw: str, business_day: date) -> bool:
    """只识别日期前缀，导入阶段不解析或改写表内时间。"""
    match = _DATE_PREFIX_RE.match(raw)
    if match is None:
        return False
    return tuple(map(int, match.groups())) == (
        business_day.year,
        business_day.month,
        business_day.day,
    )


def _identity_key(drama_name: str, platform: str, raw_time: str) -> str:
    return build_task_source_key(drama_name, platform, raw_time)


def _private_identity(raw: tuple[str, ...]) -> str:
    cells = [*raw, *([""] * 14)][:14]
    if not cells[4].strip() or not cells[5].strip() or not cells[7].strip():
        return ""
    return _identity_key(cells[5], cells[7], cells[4])


def _is_operator_row(
    row: PublicDramaRow, operator: ImportOperator, *, match_group: bool = False
) -> bool:
    group = row.cells[2].strip() if len(row.cells) > 2 else ""
    if operator.name in group:
        return True
    return match_group and group.startswith(operator.group_prefix)

from __future__ import annotations

from datetime import date

from backend.domain.imports.drama_import import (
    PublicDramaRow,
    build_import_preview,
    map_public_row,
)


def _public_row(
    row_number: int,
    *,
    available_time: str = "2026/8/17 10:09",
    drama_name: str = "虚契归真",
    platform: str = "番茄",
    iaa: str = "",
    iap_9_9: str = "",
    iap_2_9: str = "",
    owner_done: str = "",
    group: str = "B田雨-林浩东",
    validation: str = "有人未上",
) -> PublicDramaRow:
    cells = [""] * 28
    cells[0] = "测试组B"
    cells[1] = "新增重点"
    cells[2] = group
    cells[3] = "已看"
    cells[4] = available_time
    cells[5] = drama_name
    cells[6] = "素材OK"
    cells[7] = "R3已更新"
    cells[8] = "来源原名"
    cells[9] = "库好了"
    cells[10] = platform
    cells[11] = "漫剧"
    cells[12] = iaa
    cells[13] = iap_9_9
    cells[14] = iap_2_9
    cells[21] = owner_done
    cells[27] = validation
    return PublicDramaRow(row_number=row_number, cells=tuple(cells))


def test_map_public_row_uses_verified_column_mapping_and_preserves_time_text():
    source = _public_row(
        28,
        iaa="aweme://iaa",
        iap_9_9="aweme://9.9",
        iap_2_9="aweme://2.9",
        owner_done="1",
        validation="OK",
    )

    result = map_public_row(source)

    assert result.cells == (
        "测试组B",
        "新增重点",
        "B田雨-林浩东",
        "已看",
        "2026/8/17 10:09",
        "虚契归真",
        "库好了",
        "番茄",
        "漫剧",
        "aweme://iaa",
        "aweme://9.9",
        "aweme://2.9",
        "1",
        "OK",
    )
    assert result.has_validated_links is True


def test_map_public_row_keeps_background_colors_for_mapped_private_cells():
    source = _public_row(28)
    colors = [None] * 28
    colors[0] = "#d9f5d6"
    colors[2] = "#fdddef"
    colors[4] = "#fff258"
    colors[21] = "#bacefd"
    colors[27] = "#d9f3fd"
    source = PublicDramaRow(source.row_number, source.cells, tuple(colors))

    result = map_public_row(source)

    assert result.fill_colors == (
        "#d9f5d6",
        None,
        "#fdddef",
        None,
        "#fff258",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "#bacefd",
        "#d9f3fd",
    )


def test_build_preview_keeps_public_sheet_order_without_sorting_by_time():
    rows = [
        _public_row(4, available_time="2026/8/17 10:00", drama_name="剧A"),
        _public_row(5, available_time="2026/8/17 16:00", drama_name="剧B"),
        _public_row(6, available_time="2026/8/17 0:10", drama_name="剧C"),
    ]

    preview = build_import_preview(rows, [], date(2026, 8, 17))

    assert [row.drama_name for row in preview.rows] == ["剧A", "剧B", "剧C"]
    assert [row.source_row for row in preview.rows] == [4, 5, 6]


def test_build_preview_identifies_beijing_day_without_reformatting_time():
    rows = [
        _public_row(4, available_time="2026/8/17 0:01", drama_name="今日剧"),
        _public_row(5, available_time="2026/8/18 0:01", drama_name="明日剧"),
    ]

    preview = build_import_preview(rows, [], date(2026, 8, 17))

    assert preview.source_count == 1
    assert preview.new_count == 1
    assert preview.rows[0].cells[4] == "2026/8/17 0:01"


def test_build_preview_skips_existing_private_identity():
    public = [_public_row(4)]
    private_cells = [""] * 14
    private_cells[4] = "2026/8/17 10:09"
    private_cells[5] = "虚契归真"
    private_cells[7] = "番茄"

    preview = build_import_preview(
        public,
        [tuple(private_cells)],
        date(2026, 8, 17),
    )

    assert preview.new_count == 0
    assert preview.duplicate_count == 1
    assert preview.rows == ()


def test_build_preview_records_invalid_rows_without_breaking_valid_rows():
    rows = [
        _public_row(4, drama_name=""),
        _public_row(5, drama_name="有效剧"),
    ]

    preview = build_import_preview(rows, [], date(2026, 8, 17))

    assert preview.source_count == 2
    assert preview.new_count == 1
    assert preview.invalid_count == 1
    assert preview.errors[0].source_row == 4
    assert preview.errors[0].message == "剧名不能为空"


def test_build_preview_for_tianyu_includes_own_b_group_and_cross_group_mentions_only():
    rows = [
        _public_row(4, drama_name="B组全量剧", group="B陈冠鑫-熊权创"),
        _public_row(5, drama_name="跨组本人剧", group="A熊权创-田雨"),
        _public_row(6, drama_name="其他组剧", group="C刘婧雯-施凯波"),
    ]

    preview = build_import_preview(
        rows,
        [],
        date(2026, 8, 17),
        operator_name="田雨",
        match_group=True,
    )

    assert preview.source_count == 2
    assert [row.drama_name for row in preview.rows] == ["B组全量剧", "跨组本人剧"]


def test_build_preview_switches_group_and_completion_column_for_selected_operator():
    own_group = _public_row(4, drama_name="C组全量剧", group="C刘婧雯-施凯波")
    cross_group = _public_row(5, drama_name="跨组林浩东剧", group="B田雨-林浩东")
    excluded = _public_row(6, drama_name="无关剧", group="A熊权创-田雨")
    cells = list(own_group.cells)
    cells[25] = "1"
    own_group = PublicDramaRow(own_group.row_number, tuple(cells))

    preview = build_import_preview(
        [own_group, cross_group, excluded],
        [],
        date(2026, 8, 17),
        operator_name="林浩东",
        match_group=True,
    )

    assert preview.source_count == 2
    assert [row.drama_name for row in preview.rows] == ["C组全量剧", "跨组林浩东剧"]
    assert preview.rows[0].cells[12] == "1"

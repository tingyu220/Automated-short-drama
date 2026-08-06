"""飞书剧目表 annotated CSV 解析器单元测试."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.platforms.feishu.sheet_parser import parse_task_rows


SAMPLE_CSV = (
    "[row=1]测试组重点剧,备注,推广内容配置,是否已看,免费日期,剧名,备注,平台,剧集性质,J端iaa,K9.9,L2.9,M田雨,状态\n"
    "[row=2]组A,备注2,,,2026/08/06 10:00,剧A,备注,TOMATO,,linkJ,linkK,linkL,,有人未上\n"
    "[row=3]组B,,,,2026-08-06 14:30,剧B,备注,JUBIAN,,,,,,OK\n"
    "[row=4]组C,,,,2026-08-07 09:00,剧C,备注,TOMATO,,,,,,\n"
)


class TestParseTaskRows:
    """parse_task_rows 行为验证."""

    def test_parse_supports_two_time_formats(self):
        tasks = parse_task_rows(SAMPLE_CSV)

        assert len(tasks) == 3
        by_name = {task.drama_name: task for task in tasks}
        assert by_name["剧A"].available_time == datetime(
            2026, 8, 6, 2, 0, tzinfo=timezone.utc
        )
        assert by_name["剧B"].available_time == datetime(
            2026, 8, 6, 6, 30, tzinfo=timezone.utc
        )
        assert by_name["剧C"].available_time == datetime(
            2026, 8, 7, 1, 0, tzinfo=timezone.utc
        )

    def test_parse_time_binds_shanghai_then_converts_to_utc(self):
        """E 列本地时间按东八区绑定后转换为 aware UTC。"""
        tasks = parse_task_rows(SAMPLE_CSV)

        for task in tasks:
            assert task.available_time.tzinfo is not None
            assert task.available_time.utcoffset() == timedelta(0)

    def test_cross_timezone_midnight_release_maps_to_previous_utc_day(self):
        """东八区 2026-08-08 00:30 对应 UTC 2026-08-07 16:30。"""
        annotated_csv = (
            "[row=9]组H,,,,2026/08/08 00:30,剧H,备注,TOMATO,,,,,,\n"
        )

        tasks = parse_task_rows(annotated_csv)

        assert len(tasks) == 1
        assert tasks[0].available_time == datetime(
            2026, 8, 7, 16, 30, tzinfo=timezone.utc
        )

    def test_parse_maps_columns_and_row_number(self):
        task = parse_task_rows(SAMPLE_CSV)[0]

        assert task.sheet_row == 2
        assert task.id == "2"
        assert task.drama_name == "剧A"
        assert task.platform == "TOMATO"
        assert task.status == "有人未上"

    def test_parse_skips_bad_rows(self):
        annotated_csv = (
            "[row=5]组D,,,,不是时间,剧D,备注,TOMATO,,,,,,\n"
            "[row=6]只有两列\n"
            "[row=7]组E,,,,2026/08/06 10:00,,备注,TOMATO,,,,,,\n"
            "无前缀行,,,,2026/08/06 10:00,剧F,备注,TOMATO,,,,,,\n"
            "[row=8]组G,,,,2026/08/06 10:00,剧G,备注,TOMATO,,,,,,\n"
        )

        tasks = parse_task_rows(annotated_csv)

        assert [task.sheet_row for task in tasks] == [8]

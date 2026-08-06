"""飞书真实 Adapter（lark-cli）单元测试."""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from backend.platforms.feishu.feishu_adapter import FeishuAdapter


URL = "https://example.feishu.cn/sheets/shtXXX"

SAMPLE_CSV = (
    "[row=1]测试组重点剧,备注,推广内容配置,是否已看,免费日期,剧名,备注,平台,剧集性质,J端iaa,K9.9,L2.9,M田雨,状态\n"
    "[row=2]组A,备注2,,,2026/08/06 10:00,剧A,备注,TOMATO,,linkJ,linkK,linkL,,有人未上\n"
    "[row=3]组B,,,,2026-08-06 14:30,剧B,备注,JUBIAN,,,,,,OK\n"
    "[row=4]组C,,,,2026-08-07 09:00,剧C,备注,TOMATO,,,,,,\n"
)


class FakeRunner:
    """记录调用参数的 fake runner，不访问真实 lark-cli."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        return SimpleNamespace(
            stdout=self._stdout,
            returncode=self._returncode,
            stderr="",
        )


def csv_get_envelope(annotated_csv: str) -> str:
    """构造 lark-cli +csv-get 的 JSON envelope."""
    return json.dumps({"ok": True, "data": {"annotated_csv": annotated_csv}})


FETCH_ARGS = [
    "lark-cli",
    "sheets",
    "+csv-get",
    "--url",
    URL,
    "--sheet-name",
    "剧目表",
    "--range",
    "A1:N200",
    "--as",
    "user",
    "--format",
    "json",
]


class TestFeishuAdapterFetch:
    """fetch_tasks 命令与过滤验证."""

    def test_fetch_tasks_passes_expected_argv(self):
        runner = FakeRunner(stdout=csv_get_envelope(SAMPLE_CSV))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        tasks = adapter.fetch_tasks(date(2026, 8, 6))

        assert runner.calls == [FETCH_ARGS]
        assert [task.drama_name for task in tasks] == ["剧A", "剧B"]

    def test_fetch_tasks_filters_by_day(self):
        runner = FakeRunner(stdout=csv_get_envelope(SAMPLE_CSV))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        tasks = adapter.fetch_tasks(date(2026, 8, 7))

        assert [task.drama_name for task in tasks] == ["剧C"]


class TestFeishuAdapterWrite:
    """写操作 dry_run 保护与真实命令验证."""

    def test_write_links_dry_run_records_without_running(self):
        runner = FakeRunner()
        adapter = FeishuAdapter(URL, runner=runner, dry_run=True)

        adapter.write_links(
            "2",
            {"IAA": "iaa://1", "9.9": "iap://9", "2.9": "iap://2"},
        )

        assert runner.calls == []
        assert adapter.recorded_commands == [
            [
                "lark-cli",
                "sheets",
                "+csv-put",
                "--url",
                URL,
                "--sheet-name",
                "剧目表",
                "--start-cell",
                "J2",
                "--csv",
                "iaa://1,iap://9,iap://2",
                "--as",
                "user",
                "--format",
                "json",
            ]
        ]

    def test_write_completion_dry_run_records_without_running(self):
        runner = FakeRunner()
        adapter = FeishuAdapter(URL, runner=runner, dry_run=True)

        adapter.write_completion("3")

        assert runner.calls == []
        assert adapter.recorded_commands[0][-8:-4] == [
            "--start-cell",
            "M3",
            "--csv",
            "1",
        ]

    def test_write_links_executes_when_not_dry_run(self):
        runner = FakeRunner(stdout=json.dumps({"ok": True}))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        adapter.write_links("2", {"IAA": "iaa://1"})

        assert len(runner.calls) == 1
        command = runner.calls[0]
        assert command[:3] == ["lark-cli", "sheets", "+csv-put"]
        assert URL in command
        assert "剧目表" in command
        assert command[command.index("--start-cell") + 1] == "J2"

    def test_write_completion_executes_when_not_dry_run(self):
        runner = FakeRunner(stdout=json.dumps({"ok": True}))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        adapter.write_completion("3")

        assert len(runner.calls) == 1
        command = runner.calls[0]
        assert command[:3] == ["lark-cli", "sheets", "+csv-put"]
        assert URL in command
        assert "剧目表" in command
        assert command[command.index("--start-cell") + 1] == "M3"
        assert command[command.index("--csv") + 1] == "1"


class TestFeishuAdapterReadStatus:
    """read_status 读取 N 列验证."""

    def test_read_status_parses_n_column(self):
        runner = FakeRunner(stdout=csv_get_envelope("[row=5]有人未上"))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=True)

        assert adapter.read_status("5") == "有人未上"
        assert "--range" in runner.calls[0]
        assert runner.calls[0][runner.calls[0].index("--range") + 1] == "N5:N5"

    def test_read_status_returns_ok(self):
        runner = FakeRunner(stdout=csv_get_envelope("[row=6]OK"))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=True)

        assert adapter.read_status("6") == "OK"

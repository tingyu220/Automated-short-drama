"""飞书真实 Adapter（lark-cli）单元测试."""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from backend.platforms.feishu.feishu_adapter import FeishuAdapter
import backend.platforms.feishu.feishu_adapter as feishu_module
from backend.domain.rules.account_block import AccountRow


URL = "https://example.feishu.cn/sheets/shtXXX"

SAMPLE_CSV = (
    "[row=1]测试组重点剧,备注,推广内容配置,是否已看,免费日期,剧名,备注,平台,剧集性质,J端iaa,K9.9,L2.9,M田雨,状态\n"
    "[row=2]组A,备注2,,,2026/08/06 10:00,剧A,备注,TOMATO,,linkJ,linkK,linkL,,有人未上\n"
    "[row=3]组B,,,,2026-08-06 14:30,剧B,备注,JUBIAN,,,,,,OK\n"
    "[row=4]组C,,,,2026-08-07 09:00,剧C,备注,TOMATO,,,,,,\n"
    "[row=5]组D,,,,2026-08-07 00:30,剧D,备注,TOMATO,,,,,,\n"
)


class FakeRunner:
    """记录调用参数的 fake runner，不访问真实 lark-cli."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, command, **kwargs):
        self.calls.append(list(command))
        self.kwargs.append(dict(kwargs))
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

        assert [task.drama_name for task in tasks] == ["剧C", "剧D"]

    def test_fetch_tasks_captures_lark_cli_json_output(self):
        runner = FakeRunner(stdout=csv_get_envelope(SAMPLE_CSV))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        adapter.fetch_tasks(date(2026, 8, 6))

        assert runner.kwargs[0]["capture_output"] is True
        assert runner.kwargs[0]["text"] is True

    def test_windows_runner_uses_node_wrapper_for_lark_cli(self, monkeypatch):
        runner = FakeRunner(stdout=csv_get_envelope(SAMPLE_CSV))
        adapter = FeishuAdapter(URL, dry_run=False)
        adapter._runner = runner
        monkeypatch.setattr(feishu_module.subprocess, "run", runner)
        monkeypatch.setattr(feishu_module.sys, "platform", "win32")
        monkeypatch.setattr(
            feishu_module.shutil,
            "which",
            lambda name: (
                r"C:\\Node\\node.exe" if name == "node.exe"
                else r"C:\\Users\\tingyu\\AppData\\Roaming\\npm\\lark-cli.cmd"
                if name == "lark-cli.cmd" else None
            ),
        )

        adapter.fetch_tasks(date(2026, 8, 6))

        assert runner.calls[0][0].endswith("node.exe")
        assert runner.calls[0][1].endswith("scripts\\run.js")
        assert runner.calls[0][2:4] == ["sheets", "+csv-get"]


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


class TestFeishuAccountSheets:
    """账户表读取与写入命令保持平台细节在 Adapter 内。"""

    def test_read_account_rows_parses_a_to_f(self):
        annotated = (
            "[row=1]账户组,剧名,账户名称,账户ID/CID,是否测试户,启用状态\n"
            "[row=2]B1,,账户甲,cid-1,,启用\n"
            "[row=3]B4,旧剧,账户乙,cid-2,是,停用\n"
        )
        runner = FakeRunner(stdout=csv_get_envelope(annotated))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        rows = adapter.read_account_rows("IAA")

        assert [(row.row_number, row.group, row.drama_name) for row in rows] == [
            (2, "B1", ""),
            (3, "B4", "旧剧"),
        ]
        assert rows[0].enabled is True
        assert rows[0].is_test is False
        assert rows[1].enabled is False
        assert rows[1].is_test is True
        command = runner.calls[0]
        assert command[command.index("--sheet-name") + 1] == "iaa账户"
        assert command[command.index("--range") + 1] == "A1:F500"

    def test_write_account_names_targets_drama_column(self):
        runner = FakeRunner(stdout=json.dumps({"ok": True}))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        adapter.write_account_names("IAP", {8: "新剧", 9: "新剧", 10: "新剧"})

        command = runner.calls[0]
        assert command[command.index("--sheet-name") + 1] == "iap账户"
        assert command[command.index("--start-cell") + 1] == "B8"
        assert command[command.index("--csv") + 1] == "新剧\n新剧\n新剧"

    def test_write_account_names_dry_run_has_no_external_call(self):
        runner = FakeRunner()
        adapter = FeishuAdapter(URL, runner=runner, dry_run=True)

        adapter.write_account_names("IAA", {2: "新剧"})

        assert runner.calls == []
        assert adapter.recorded_commands[0][adapter.recorded_commands[0].index("--sheet-name") + 1] == "iaa账户"

    def test_write_account_test_flag_targets_column_e(self):
        runner = FakeRunner(stdout=json.dumps({"ok": True}))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)

        adapter.write_account_test_flags("IAA", {5})

        command = runner.calls[0]
        assert command[command.index("--sheet-name") + 1] == "iaa账户"
        assert command[command.index("--start-cell") + 1] == "E5"
        assert command[command.index("--csv") + 1] == "是"

    def test_append_account_block_copies_only_template_columns(self):
        runner = FakeRunner(stdout=json.dumps({"ok": True}))
        adapter = FeishuAdapter(URL, runner=runner, dry_run=False)
        template = [
            AccountRow(2, "账户甲", "cid-1", "B1", True, True, "旧剧"),
            AccountRow(3, "账户乙", "cid-2", "B1", True, False, "旧剧"),
        ]

        appended = adapter.append_account_block("IAA", 10, template)

        command = runner.calls[0]
        assert command[command.index("--sheet-name") + 1] == "iaa账户"
        assert command[command.index("--start-cell") + 1] == "A11"
        assert command[command.index("--csv") + 1] == (
            "B1,,账户甲,cid-1,,启用\n"
            "B1,,账户乙,cid-2,,启用"
        )
        assert [row.row_number for row in appended] == [11, 12]
        assert all(row.drama_name == "" and row.is_test is False for row in appended)

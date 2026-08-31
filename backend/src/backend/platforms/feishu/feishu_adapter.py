"""飞书真实 Adapter（lark-cli 版）."""
from __future__ import annotations

import csv
import io
import json
import logging
import shutil
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from backend.domain.common.timezones import SHANGHAI_TZ, as_utc
from backend.domain.errors.domain_error import ExternalAdapterError, ValidationError
from backend.domain.ports.adapters import FeishuAdapter as FeishuAdapterProtocol
from backend.domain.tasks.drama_task import DramaTask
from backend.domain.rules.account_block import AccountRow
from backend.platforms.feishu.sheet_parser import parse_annotated_rows, parse_task_rows


logger = logging.getLogger(__name__)

_FETCH_RANGE = "A1:N200"
_LINK_COLUMNS = {"IAA": "J", "9.9": "K", "2.9": "L"}
_LINK_ORDER = ("IAA", "9.9", "2.9")
_ACCOUNT_SHEETS = {"IAA": "iaa账户", "IAP": "iap账户", "TEST": "测试户账户"}
_ACCOUNT_RANGE = "A1:F500"


class FeishuAdapter(FeishuAdapterProtocol):
    """通过 lark-cli 读写飞书剧目表；dry_run 下写命令只记录不执行。

    task_id 使用飞书剧目表行号（字符串），便于回写 J/K/L/M/N 对应行。
    """

    def __init__(
        self,
        task_sheet_url: str,
        task_sheet_name: str = "剧目表",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        dry_run: bool = True,
    ) -> None:
        self._task_sheet_url = task_sheet_url
        self._task_sheet_name = task_sheet_name
        self._runner = runner
        self._dry_run = dry_run
        self._recorded_commands: list[list[str]] = []

    def fetch_tasks(self, day: date) -> list[DramaTask]:
        """读取剧目表并过滤指定日期的投放任务。"""
        command = self._read_command("+csv-get", "--range", _FETCH_RANGE)
        result = self._run(command)
        annotated_csv = _annotated_csv(result)
        local_start = datetime.combine(day, time.min, tzinfo=SHANGHAI_TZ)
        local_end = datetime.combine(
            day + timedelta(days=1),
            time.min,
            tzinfo=SHANGHAI_TZ,
        )
        start_utc = as_utc(local_start)
        end_utc = as_utc(local_end)
        return [
            task
            for task in parse_task_rows(annotated_csv)
            if start_utc <= task.available_time < end_utc
        ]

    def write_links(self, task_id: str, links: dict[str, str]) -> None:
        """把 IAA/9.9/2.9 链接回填到对应行的 J/K/L。"""
        row = self._row_number(task_id)
        values = [links.get(link_type, "") for link_type in _LINK_ORDER]
        if not any(values):
            return
        command = self._write_command("+csv-put", f"J{row}", _to_csv_row(values))
        self._run_write(command)

    def write_completion(self, task_id: str) -> None:
        """任务完成后在对应行 M 列写 1。"""
        row = self._row_number(task_id)
        command = self._write_command("+csv-put", f"M{row}", "1")
        self._run_write(command)

    def read_status(self, task_id: str) -> str:
        """读取对应行 N 列，返回 OK / 有人未上 / 其他值。"""
        row = self._row_number(task_id)
        command = self._read_command("+csv-get", "--range", f"N{row}:N{row}")
        result = self._run(command)
        for row_number, cells in parse_annotated_rows(_annotated_csv(result)):
            if row_number == row and cells:
                return cells[0].strip()
        return ""

    def read_account_rows(self, kind: str) -> list[AccountRow]:
        """读取账户表 A-F，转换为平台无关账户行。"""
        sheet_name = self._account_sheet_name(kind)
        result = self._run(
            self._read_command(
                "+csv-get",
                "--range",
                _ACCOUNT_RANGE,
                sheet_name=sheet_name,
            )
        )
        rows: list[AccountRow] = []
        for row_number, cells in parse_annotated_rows(_annotated_csv(result)):
            if row_number == 1 or len(cells) < 4:
                continue
            padded = [*cells, "", ""][:6]
            group, drama_name, name, cid, is_test, enabled = (
                value.strip() for value in padded
            )
            if not group or not cid:
                continue
            rows.append(
                AccountRow(
                    row_number=row_number,
                    name=name,
                    cid=cid,
                    group=group,
                    enabled=enabled.lower() in {"启用", "是", "true", "1", "enabled"},
                    is_test=is_test.lower() in {"是", "true", "1", "yes"},
                    drama_name=drama_name,
                )
            )
        return rows

    def write_account_names(self, kind: str, assignments: dict[int, str]) -> None:
        """按连续行批量写账户表 B 列剧名；空计划不执行。"""
        if not assignments:
            return
        sheet_name = self._account_sheet_name(kind)
        for rows in _contiguous_assignment_groups(assignments):
            start = rows[0]
            csv_text = _to_csv_column([assignments[row] for row in rows])
            self._run_write(
                self._write_command(
                    "+csv-put",
                    f"B{start}",
                    csv_text,
                    sheet_name=sheet_name,
                )
            )

    def write_account_test_flags(self, kind: str, row_numbers: set[int]) -> None:
        """把选中的测试户行 E 列标记为“是”。"""
        if not row_numbers:
            return
        sheet_name = self._account_sheet_name(kind)
        assignments = {row: "是" for row in row_numbers}
        for rows in _contiguous_assignment_groups(assignments):
            self._run_write(
                self._write_command(
                    "+csv-put",
                    f"E{rows[0]}",
                    _to_csv_column(["是"] * len(rows)),
                    sheet_name=sheet_name,
                )
            )

    def append_account_block(
        self,
        kind: str,
        expected_last_row: int,
        template_rows: list[AccountRow],
    ) -> list[AccountRow]:
        """在预期表尾复制标准块；剧名、测试标记和备注保持为空。"""
        if not template_rows:
            return []
        if expected_last_row < 1:
            raise ValidationError("账户表最后行号必须为正整数")
        sheet_name = self._account_sheet_name(kind)
        values = [
            [
                row.group,
                "",
                row.name,
                row.cid,
                "",
                "启用" if row.enabled else "停用",
            ]
            for row in template_rows
        ]
        self._run_write(
            self._write_command(
                "+csv-put",
                f"A{expected_last_row + 1}",
                _to_csv_rows(values),
                sheet_name=sheet_name,
            )
        )
        return [
            AccountRow(
                row_number=expected_last_row + offset,
                name=row.name,
                cid=row.cid,
                group=row.group,
                enabled=row.enabled,
                is_test=False,
                drama_name="",
            )
            for offset, row in enumerate(template_rows, start=1)
        ]

    @property
    def recorded_commands(self) -> list[list[str]]:
        """dry_run 模式下记录但未执行的命令（仅供测试/日志观察）。"""
        return [list(command) for command in self._recorded_commands]

    def _read_command(
        self,
        shortcut: str,
        *extra: str,
        sheet_name: str | None = None,
    ) -> list[str]:
        return [
            "lark-cli",
            "sheets",
            shortcut,
            "--url",
            self._task_sheet_url,
            "--sheet-name",
            sheet_name or self._task_sheet_name,
            *extra,
            "--as",
            "user",
            "--format",
            "json",
        ]

    def _write_command(
        self,
        shortcut: str,
        start_cell: str,
        csv_text: str,
        *,
        sheet_name: str | None = None,
    ) -> list[str]:
        return [
            "lark-cli",
            "sheets",
            shortcut,
            "--url",
            self._task_sheet_url,
            "--sheet-name",
            sheet_name or self._task_sheet_name,
            "--start-cell",
            start_cell,
            "--csv",
            csv_text,
            "--as",
            "user",
            "--format",
            "json",
        ]

    @staticmethod
    def _account_sheet_name(kind: str) -> str:
        try:
            return _ACCOUNT_SHEETS[kind.upper()]
        except KeyError as exc:
            raise ValidationError(f"不支持的账户表类型: {kind!r}") from exc

    def _run_write(self, command: list[str]) -> None:
        if self._dry_run:
            self._recorded_commands.append(command)
            logger.info("dry-run 不执行 lark-cli 写命令: %s", command)
            return
        self._run(command)

    def _run(self, command: list[str]) -> Any:
        command = self._resolve_command(command)
        try:
            completed = self._runner(
                command,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
        except Exception as exc:
            raise ExternalAdapterError(f"lark-cli 执行失败: {exc}") from exc
        if getattr(completed, "returncode", 0) != 0:
            raise ExternalAdapterError(
                f"lark-cli 命令失败: {' '.join(command)}"
                f" stderr={getattr(completed, 'stderr', '')}"
            )
        return completed

    def _resolve_command(self, command: list[str]) -> list[str]:
        """Windows 下通过 Node 运行 lark-cli，避免 .cmd 无法被 subprocess 直接执行。"""
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

    @staticmethod
    def _row_number(task_id: str) -> int:
        try:
            row = int(task_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"task_id 必须是飞书表行号: {task_id!r}") from exc
        if row < 1:
            raise ValidationError(f"task_id 必须是正整数行号: {task_id!r}")
        return row


def _annotated_csv(completed: Any) -> str:
    envelope = _load_json(_stdout_text(completed))
    annotated_csv = (envelope.get("data") or {}).get("annotated_csv")
    if not isinstance(annotated_csv, str):
        raise ExternalAdapterError("lark-cli 响应缺少 data.annotated_csv")
    return annotated_csv


def _load_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ExternalAdapterError(f"lark-cli 输出不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExternalAdapterError("lark-cli 输出 JSON 必须是对象")
    return data


def _stdout_text(completed: Any) -> str:
    stdout = getattr(completed, "stdout", "")
    if isinstance(stdout, bytes):
        return stdout.decode("utf-8", errors="replace")
    return "" if stdout is None else str(stdout)


def _to_csv_row(values: list[str]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerow(values)
    return buffer.getvalue().rstrip("\r\n")


def _to_csv_column(values: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for value in values:
        writer.writerow([value])
    return buffer.getvalue().rstrip("\n")


def _to_csv_rows(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue().rstrip("\n")


def _contiguous_assignment_groups(assignments: dict[int, str]) -> list[list[int]]:
    groups: list[list[int]] = []
    for row in sorted(assignments):
        if row < 1:
            raise ValidationError(f"账户表行号必须为正整数: {row!r}")
        if not groups or row != groups[-1][-1] + 1:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups

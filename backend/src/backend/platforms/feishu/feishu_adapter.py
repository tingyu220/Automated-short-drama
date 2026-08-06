"""飞书真实 Adapter（lark-cli 版）."""
from __future__ import annotations

import csv
import io
import json
import logging
import subprocess
from datetime import date, datetime, time, timedelta
from typing import Any, Callable

from backend.domain.common.timezones import SHANGHAI_TZ, as_utc
from backend.domain.errors.domain_error import ExternalAdapterError, ValidationError
from backend.domain.ports.adapters import FeishuAdapter as FeishuAdapterProtocol
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.feishu.sheet_parser import parse_annotated_rows, parse_task_rows


logger = logging.getLogger(__name__)

_FETCH_RANGE = "A1:N200"
_LINK_COLUMNS = {"IAA": "J", "9.9": "K", "2.9": "L"}
_LINK_ORDER = ("IAA", "9.9", "2.9")


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

    @property
    def recorded_commands(self) -> list[list[str]]:
        """dry_run 模式下记录但未执行的命令（仅供测试/日志观察）。"""
        return [list(command) for command in self._recorded_commands]

    def _read_command(self, shortcut: str, *extra: str) -> list[str]:
        return [
            "lark-cli",
            "sheets",
            shortcut,
            "--url",
            self._task_sheet_url,
            "--sheet-name",
            self._task_sheet_name,
            *extra,
            "--as",
            "user",
            "--format",
            "json",
        ]

    def _write_command(self, shortcut: str, start_cell: str, csv_text: str) -> list[str]:
        return [
            "lark-cli",
            "sheets",
            shortcut,
            "--url",
            self._task_sheet_url,
            "--sheet-name",
            self._task_sheet_name,
            "--start-cell",
            start_cell,
            "--csv",
            csv_text,
            "--as",
            "user",
            "--format",
            "json",
        ]

    def _run_write(self, command: list[str]) -> None:
        if self._dry_run:
            self._recorded_commands.append(command)
            logger.info("dry-run 不执行 lark-cli 写命令: %s", command)
            return
        self._run(command)

    def _run(self, command: list[str]) -> Any:
        try:
            completed = self._runner(command)
        except Exception as exc:
            raise ExternalAdapterError(f"lark-cli 执行失败: {exc}") from exc
        if getattr(completed, "returncode", 0) != 0:
            raise ExternalAdapterError(
                f"lark-cli 命令失败: {' '.join(command)}"
                f" stderr={getattr(completed, 'stderr', '')}"
            )
        return completed

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

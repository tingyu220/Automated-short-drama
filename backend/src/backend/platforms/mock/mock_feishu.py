"""飞书 Adapter Mock 实现 —— 内存态、确定性、无网络."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from copy import deepcopy

from backend.domain.common.timezones import SHANGHAI_TZ, as_utc
from backend.domain.ports.adapters import FeishuAdapter
from backend.domain.tasks.drama_task import DramaTask
from backend.domain.rules.account_block import AccountRow
from backend.platforms.mock.mock_account_table import MOCK_ACCOUNT_ROWS


class MockFeishuAdapter(FeishuAdapter):
    """内存态飞书表 Mock，支持注入任务."""

    def __init__(
        self,
        tasks: list[DramaTask] | None = None,
        account_rows: list[AccountRow] | None = None,
    ):
        self._tasks = tasks
        self._written_links: dict[str, dict[str, str]] = {}
        self._completed: set[str] = set()
        rows = MOCK_ACCOUNT_ROWS if account_rows is None else account_rows
        self._account_rows = {
            "IAA": [deepcopy(row) for row in rows if row.group in {"B1", "B4", "B7", "BX"}],
            "IAP": [deepcopy(row) for row in rows if row.group in {"B1-9.9", "B2-2.9"}],
            "TEST": [],
        }

    def fetch_tasks(self, day: date) -> list[DramaTask]:
        if self._tasks is None:
            return self._sample_tasks(day)
        return [
            task
            for task in self._tasks
            if _in_local_day(task.available_time, day)
        ]

    def write_links(self, task_id: str, links: dict[str, str]) -> None:
        self._written_links[task_id] = dict(links)

    def write_completion(self, task_id: str) -> None:
        self._completed.add(task_id)

    def read_status(self, task_id: str) -> str:
        return "OK" if task_id in self._completed else "PENDING"

    def read_account_rows(self, kind: str) -> list[AccountRow]:
        return deepcopy(self._account_rows[kind.upper()])

    def write_account_names(self, kind: str, assignments: dict[int, str]) -> None:
        by_row = {
            row.row_number: row for row in self._account_rows[kind.upper()]
        }
        for row_number, drama_name in assignments.items():
            by_row[row_number].drama_name = drama_name

    def write_account_test_flags(self, kind: str, row_numbers: set[int]) -> None:
        by_row = {
            row.row_number: row for row in self._account_rows[kind.upper()]
        }
        for row_number in row_numbers:
            by_row[row_number].is_test = True

    def append_account_block(
        self,
        kind: str,
        expected_last_row: int,
        template_rows: list[AccountRow],
    ) -> list[AccountRow]:
        appended = [
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
        self._account_rows[kind.upper()].extend(deepcopy(appended))
        return deepcopy(appended)

    @property
    def written_links(self) -> dict[str, dict[str, str]]:
        """已写入链接的内存快照（仅供测试观察）."""
        return {task_id: dict(links) for task_id, links in self._written_links.items()}

    @staticmethod
    def _sample_tasks(day: date) -> list[DramaTask]:
        base_time = datetime.combine(day, time(10, 0), tzinfo=timezone.utc)
        suffix = day.strftime("%Y%m%d")
        return [
            DramaTask(
                id=f"mock-feishu-tomato-{suffix}",
                drama_name="示例短剧A",
                platform="TOMATO",
                available_time=base_time,
            ),
            DramaTask(
                id=f"mock-feishu-jubian-{suffix}",
                drama_name="示例短剧B",
                platform="JUBIAN",
                available_time=base_time,
            ),
        ]


def _in_local_day(available_time: datetime, day: date) -> bool:
    """判断 aware UTC 投放时间是否落在本地东八区指定日期。"""
    local_start = datetime.combine(day, time.min, tzinfo=SHANGHAI_TZ)
    local_end = datetime.combine(
        day + timedelta(days=1),
        time.min,
        tzinfo=SHANGHAI_TZ,
    )
    value = as_utc(available_time)
    return as_utc(local_start) <= value < as_utc(local_end)

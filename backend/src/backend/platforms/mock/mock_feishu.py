"""飞书 Adapter Mock 实现 —— 内存态、确定性、无网络."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from backend.domain.ports.adapters import FeishuAdapter
from backend.domain.tasks.drama_task import DramaTask


class MockFeishuAdapter(FeishuAdapter):
    """内存态飞书表 Mock，支持注入任务."""

    def __init__(self, tasks: list[DramaTask] | None = None):
        self._tasks = tasks
        self._written_links: dict[str, dict[str, str]] = {}
        self._completed: set[str] = set()

    def fetch_tasks(self, day: date) -> list[DramaTask]:
        if self._tasks is None:
            return self._sample_tasks(day)
        return [task for task in self._tasks if task.available_time.date() == day]

    def write_links(self, task_id: str, links: dict[str, str]) -> None:
        self._written_links[task_id] = dict(links)

    def write_completion(self, task_id: str) -> None:
        self._completed.add(task_id)

    def read_status(self, task_id: str) -> str:
        return "OK" if task_id in self._completed else "PENDING"

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

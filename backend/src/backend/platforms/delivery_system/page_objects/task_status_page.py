"""投放系统任务状态页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"


class TaskStatusPage:
    """按外部任务 ID 定位任务行并读取标准状态."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def poll(self, external_task_id: str) -> str:
        """读取任务行状态并归一化：已完成/部分失败/失败/其他."""
        selector = (
            f"{self._selectors['task_row']}:has-text('{external_task_id}') "
            f"{self._selectors['task_status_cell']}"
        )
        raw = (self._page.locator(selector).text_content() or "").strip()
        if not raw:
            raise ExternalAdapterError(
                f"未找到任务 {external_task_id} 的状态，结果不确定",
                code=RESULT_UNCERTAIN,
            )
        upper = raw.upper()
        if "已完成" in raw or "COMPLETED" in upper:
            return "COMPLETED"
        if "部分失败" in raw or "PARTIAL_FAILED" in upper:
            return "PARTIAL_FAILED"
        if "失败" in raw or "FAILED" in upper:
            return "FAILED"
        return "OTHER"

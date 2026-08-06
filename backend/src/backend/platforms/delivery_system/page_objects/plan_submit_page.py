"""投放系统标准计划提交页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"


class PlanSubmitPage:
    """标准计划填写与提交，结果不确定时按 RESULT_UNCERTAIN 报错."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def submit(self, plan_spec: Any) -> str:
        """提交计划并读取外部任务 ID；未读到任务 ID 视为结果不确定."""
        del plan_spec  # 页面字段由计划页状态承载，Adapter 只负责触发提交
        self._page.goto(self._selectors["base_url"])
        self._page.locator(self._selectors["plan_submit_button"]).click()
        self._page.locator(self._selectors["confirm_submit_button"]).click()
        task_id = (
            self._page.locator(self._selectors["task_row"]).text_content() or ""
        ).strip()
        if not task_id:
            raise ExternalAdapterError(
                "计划提交后未读到外部任务 ID，结果不确定",
                code=RESULT_UNCERTAIN,
            )
        return task_id

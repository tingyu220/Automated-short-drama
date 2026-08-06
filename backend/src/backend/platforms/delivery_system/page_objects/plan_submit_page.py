"""投放系统标准计划提交页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ConfigurationError, ExternalAdapterError
from backend.domain.plans.plan_spec import PlanSpec


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"
_PLAN_FORM_FIELDS = (
    "plan_task_name",
    "plan_account_cid",
    "plan_product",
    "plan_promotion_config",
)


class PlanSubmitPage:
    """标准计划填写与提交，结果不确定时按 RESULT_UNCERTAIN 报错."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def submit(self, plan_spec: PlanSpec) -> str:
        """按 PlanSpec 填写计划表单并提交，未读到任务 ID 视为结果不确定."""
        self._require_plan_selectors()
        self._page.goto(self._selectors["base_url"])
        self._page.locator(self._selectors["plan_task_name"]).fill(plan_spec.task_name)
        first_cid = (plan_spec.account_cids or [""])[0]
        self._page.locator(self._selectors["plan_account_cid"]).fill(first_cid)
        self._page.locator(self._selectors["plan_product"]).fill(
            plan_spec.product_id or ""
        )
        # 领域模型暂无独立推广配置 ID，暂以首个推广链接作为推广内容
        promotion_config = next(iter(plan_spec.link_set.values()), "")
        self._page.locator(self._selectors["plan_promotion_config"]).fill(
            promotion_config
        )
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

    def _require_plan_selectors(self) -> None:
        missing = [key for key in _PLAN_FORM_FIELDS if key not in self._selectors]
        if missing:
            raise ConfigurationError(f"投放计划表单缺少选择器: {', '.join(missing)}")

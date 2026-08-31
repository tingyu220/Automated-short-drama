"""投放系统标准计划提交页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ConfigurationError, ExternalAdapterError
from backend.domain.plans.delivery_form_spec import DeliveryFormSpec


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"
_PLAN_FORM_FIELDS = (
    "plan_task_name",
    "plan_type",
    "plan_account_cid",
    "plan_douyin_account",
    "plan_account_open_preset",
    "plan_ad_preset",
    "plan_promotion_config",
    "plan_material",
    "plan_title_package",
    "plan_title_shuffle_button",
    "plan_project_rule",
    "plan_ad_rule",
    "plan_material_average",
    "plan_title_average",
    "plan_material_group_count",
    "plan_ad_limit",
    "plan_project_count",
    "plan_submit_button",
    "confirm_submit_button",
    "task_row",
)


class PlanSubmitPage:
    """标准计划填写与提交，结果不确定时按 RESULT_UNCERTAIN 报错."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def fill(self, form: DeliveryFormSpec) -> None:
        """严格填写全部表单数据；只要契约或选择器缺失就不触发提交。"""
        self._require_plan_selectors()
        self._page.goto(self._selectors["base_url"])
        self._page.locator(self._selectors["plan_task_name"]).fill(form.task_name)
        self._page.locator(self._selectors["plan_type"]).fill(form.plan_type)
        for index, row in enumerate(form.cid_rows):
            values = {
                "plan_account_cid": row.cid,
                "plan_douyin_account": row.douyin_account,
                "plan_account_open_preset": row.account_open_preset,
                "plan_ad_preset": row.ad_preset,
                "plan_promotion_config": row.promotion_content,
            }
            for key, value in values.items():
                self._page.locator(
                    self._selectors[key].format(index=index)
                ).fill(value)
        for index, material_id in enumerate(form.material_ids):
            self._page.locator(
                self._selectors["plan_material"].format(index=index)
            ).fill(material_id)
        for index, title_package in enumerate(form.title_packages):
            self._page.locator(
                self._selectors["plan_title_package"].format(index=index)
            ).fill(title_package)
        self._page.locator(self._selectors["plan_project_rule"]).fill(
            form.project_rule
        )
        self._page.locator(self._selectors["plan_ad_rule"]).fill(form.ad_rule)
        self._page.locator(self._selectors["plan_material_average"]).fill(
            "开启" if form.material_average_enabled else "关闭"
        )
        self._page.locator(self._selectors["plan_title_average"]).fill(
            "开启" if form.title_average_enabled else "关闭"
        )
        self._page.locator(self._selectors["plan_material_group_count"]).fill(
            str(form.material_group_count)
        )
        self._page.locator(self._selectors["plan_ad_limit"]).fill(
            str(form.ad_limit_per_project)
        )
        self._page.locator(self._selectors["plan_project_count"]).fill(
            str(form.project_count)
        )
        if form.shuffle_titles_once:
            self._page.locator(
                self._selectors["plan_title_shuffle_button"]
            ).click()

    def submit(self, form: DeliveryFormSpec) -> str:
        """先完整填写，再执行唯一一次提交与确认。"""
        self.fill(form)
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

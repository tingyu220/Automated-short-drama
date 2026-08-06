"""投放系统推广内容配置页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError


DEFAULT_DISTRIBUTOR = "微智造"
PROMOTION_LINK_DRAMA_MISMATCH = "PROMOTION_LINK_DRAMA_MISMATCH"
RESULT_UNCERTAIN = "RESULT_UNCERTAIN"
_MISMATCH_KEYWORDS = ("DRAMA_MISMATCH", "剧名不匹配", "主剧不匹配")


class PromotionConfigPage:
    """推广内容配置操作：搜索缺失项、创建并校验主剧与链接匹配."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def search(self, name: str) -> list[str]:
        """按配置名称搜索，返回名称匹配的搜索结果行文本."""
        self._page.goto(self._selectors["base_url"])
        self._page.locator(self._selectors["config_search_input"]).fill(name)
        self._page.locator(self._selectors["config_search_input"]).press("Enter")
        rows = self._page.locator(self._selectors["config_row"]).evaluate_all(
            "(rows) => rows.map(row => row.innerText.trim())"
        )
        return [row for row in rows if name in row]

    def create_missing(self, name: str, link: str, drama_name: str) -> str:
        """只创建缺失配置；保存后读校验结果，主剧不匹配立即报错."""
        existing = self.search(name)
        if existing:
            return existing[0]
        self._page.locator(self._selectors["config_create_button"]).click()
        self._page.locator(self._selectors["config_name_input"]).fill(name)
        self._page.locator(self._selectors["config_main_drama"]).fill(drama_name)
        self._page.locator(self._selectors["config_distributor"]).fill(
            DEFAULT_DISTRIBUTOR
        )
        self._page.locator(self._selectors["config_link_input"]).fill(link)
        self._page.locator(self._selectors["config_save_button"]).click()
        result = (
            self._page.locator(self._selectors["task_status_cell"]).text_content()
            or ""
        ).strip()
        if any(keyword in result for keyword in _MISMATCH_KEYWORDS):
            raise ExternalAdapterError(
                f"推广链接与主剧不匹配: {result}",
                code=PROMOTION_LINK_DRAMA_MISMATCH,
            )
        if not result:
            raise ExternalAdapterError(
                "推广内容配置保存后未读到校验结果，结果不确定",
                code=RESULT_UNCERTAIN,
            )
        return result

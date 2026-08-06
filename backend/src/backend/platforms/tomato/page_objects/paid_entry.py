"""番茄付费入口页面对象."""
from __future__ import annotations

import re
from typing import Any

from backend.domain.ports.adapters import TemplateInfo


class PaidEntryPage:
    """付费入口操作：扫描 IAP 模板并生成推广链接."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def _goto(self) -> None:
        self._page.goto(self._selectors["login_url"])

    def scan_templates(self, drama_name: str) -> list[TemplateInfo]:
        """扫描全部模板项，读取档位价格与页面顺序."""
        self._goto()
        rows = self._page.locator(self._selectors["template_item"]).evaluate_all(
            """
            (items, selectors) => items.map(item => {
              const price = item.querySelector(selectors.tier_price);
              const order = item.querySelector(selectors.page_order);
              return [price ? price.textContent : "", order ? order.textContent : ""];
            })
            """,
            {
                "tier_price": self._selectors["tier_price"],
                "page_order": self._selectors["page_order"],
            },
        )
        return [
            TemplateInfo(
                template_id="",
                drama_name=drama_name,
                title="",
                price=_parse_float(price_text),
                page_order=_parse_int(order_text),
            )
            for price_text, order_text in rows
        ]

    def generate_link(self, template: TemplateInfo) -> str:
        """点击目标模板并生成推广链接."""
        self._goto()
        self._page.get_by_text(template.title).click()
        self._page.locator(self._selectors["generate_button"]).click()
        return _read_link(self._page, self._selectors)


def _read_link(page: Any, selectors: dict[str, str]) -> str:
    """优先读取输入框值，为空时回退到剪贴板."""
    link_input = page.locator(selectors["link_input"])
    url = link_input.input_value()
    if url:
        return url
    return str(page.evaluate("navigator.clipboard.readText()"))


def _parse_float(text: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group(0)) if match else 0.0


def _parse_int(text: str) -> int:
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0

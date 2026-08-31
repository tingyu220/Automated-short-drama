"""番茄付费入口页面对象."""
from __future__ import annotations

import re
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError
from backend.domain.ports.adapters import TemplateInfo


class PaidEntryPage:
    """付费入口操作：扫描 IAP 模板并生成推广链接."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def scan_templates(self, drama_name: str) -> list[TemplateInfo]:
        """扫描全部模板项，读取模板标题、档位价格与页面顺序."""
        item_count = self._page.locator(self._selectors["template_item"]).count()
        rows = self._page.locator(self._selectors["template_item"]).evaluate_all(
            """
            (items, selectors) => items.map(item => {
              const title = item.querySelector(selectors.template_title);
              const price = item.querySelector(selectors.tier_price);
              const order = item.querySelector(selectors.page_order);
              return [
                title ? title.textContent.trim() : "",
                price ? price.textContent : "",
                order ? order.textContent : ""
              ];
            })
            """,
            {
                "template_title": self._selectors["template_title"],
                "tier_price": self._selectors["tier_price"],
                "page_order": self._selectors["page_order"],
            },
        )
        if not rows and "promotion_modal" in self._selectors:
            return self._scan_drawer_templates(drama_name)
        return [
            TemplateInfo(
                template_id=title_text,
                drama_name=drama_name,
                title=title_text,
                price=_parse_float(price_text),
                page_order=_parse_int(order_text),
            )
            for title_text, price_text, order_text in rows
        ]

    def _scan_drawer_templates(self, drama_name: str) -> list[TemplateInfo]:
        """读取真实推广链抽屉；每个模板只取档位1支付金额。"""
        self._page.locator(self._selectors["generate_button"]).click()
        self._page.locator(self._selectors["promotion_modal"]).first.wait_for()
        template_select = self._page.locator(self._selectors["template_select"])
        template_select.click()
        options = self._page.locator(self._selectors["template_option"])
        self._wait_for_options(options)
        titles = options.all_text_contents()
        drawer = self._page.locator(self._selectors["promotion_modal"])
        templates: list[TemplateInfo] = []
        for order, raw_title in enumerate(titles, start=1):
            title = str(raw_title).strip()
            if not title:
                continue
            if order > 1:
                template_select.click()
                options = self._page.locator(self._selectors["template_option"])
                self._wait_for_options(options)
            options.nth(order - 1).click()
            self._page.wait_for_timeout(300)
            amounts = drawer.evaluate(
                """element => Array.from(element.querySelectorAll('*'))
                    .map(node => (node.textContent || '').trim())
                    .filter(text => /^\\d+(?:\\.\\d+)?元$/.test(text))
                    .map(text => Number.parseFloat(text))"""
            )
            first_tier = float(amounts[0]) if amounts else 0.0
            templates.append(
                TemplateInfo(
                    template_id=title,
                    drama_name=drama_name,
                    title=title,
                    price=first_tier,
                    page_order=order,
                )
            )
        return templates

    def generate_link(self, template: TemplateInfo) -> str:
        """在推广链抽屉中选择目标模板并读取推广链接。"""
        template_title = template.title or template.template_id
        self._page.locator(self._selectors["generate_button"]).click()
        self._page.locator(self._selectors["promotion_modal"]).first.wait_for()
        template_select = self._page.locator(self._selectors["template_select"])
        template_select.click()
        options = self._page.locator(self._selectors["template_option"])
        self._wait_for_options(options)
        titles = options.all_text_contents()
        selected_index = next(
            (
                index
                for index, title in enumerate(titles)
                if str(title).strip() == template_title.strip()
            ),
            None,
        )
        if selected_index is None:
            # 先检查禁用选项里有没有——有则说明该模板已生成过链接
            disabled_selector = self._selectors.get("template_option_disabled")
            disabled_options: list[str] = []
            if disabled_selector:
                disabled = self._page.locator(disabled_selector)
                if disabled.count() > 0:
                    disabled_options = [
                        str(text).strip()
                        for text in disabled.all_text_contents()
                    ]
            if template_title.strip() in disabled_options:
                raise ExternalAdapterError(
                    "番茄推广链模板已生成过链接，选项被禁用",
                    code="TOMATO_TEMPLATE_ALREADY_GENERATED",
                    details={
                        "expected_template": template_title,
                        "available_templates": [str(title).strip() for title in titles],
                        "disabled_templates": disabled_options,
                    },
                )
            raise ExternalAdapterError(
                "番茄推广链抽屉中未找到目标付费模板",
                code="TOMATO_TEMPLATE_OPTION_MISSING",
                details={
                    "expected_template": template_title,
                    "available_templates": [str(title).strip() for title in titles],
                    "disabled_templates": disabled_options,
                },
            )
        options.nth(selected_index).click()
        # 表单已覆盖页面，必须点击抽屉内确认按钮，不能误点底层生成按钮。
        self._page.locator(self._selectors["confirm_button"]).click()
        return _read_link(self._page, self._selectors)

    def _wait_for_options(self, options: Any) -> None:
        try:
            options.first.wait_for()
        except Exception as exc:
            all_count = _safe_count(
                self._page,
                self._selectors.get("template_option_all"),
            )
            disabled_count = _safe_count(
                self._page,
                self._selectors.get("template_option_disabled"),
            )
            reason = "OPTIONS_NOT_LOADED"
            if all_count is not None and all_count > 0:
                reason = (
                    "ALL_OPTIONS_ALREADY_CREATED"
                    if disabled_count == all_count
                    else "NO_ENABLED_OPTIONS"
                )
            raise ExternalAdapterError(
                "番茄付费建链抽屉未加载可用模板",
                code="TOMATO_TEMPLATE_OPTIONS_EMPTY",
                details={
                    "selector": self._selectors["template_option"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "reason": reason,
                    "visible_option_count": all_count,
                    "visible_disabled_option_count": disabled_count,
                },
            ) from exc


def _safe_count(page: Any, selector: str | None) -> int | None:
    if not selector:
        return None
    try:
        return int(page.locator(selector).count())
    except Exception:
        return None


def _read_link(page: Any, selectors: dict[str, str]) -> str:
    """优先读取 result_link 文本，超时后回退到 link_input，最后回退到剪贴板."""
    if "result_link" in selectors:
        try:
            el = page.locator(selectors["result_link"])
            if el.count() > 0:
                result = el.text_content()
                if isinstance(result, str) and result.strip().startswith("aweme://"):
                    return result.strip()
        except Exception:
            pass
    try:
        link_input = page.locator(selectors["link_input"])
        link_input.wait_for(state="visible", timeout=10000)
        url = link_input.input_value()
        if url:
            return url
    except Exception:
        pass
    try:
        clipboard = page.evaluate("navigator.clipboard.readText()")
        if isinstance(clipboard, str) and clipboard.strip():
            return clipboard.strip()
    except Exception:
        pass
    return ""


def _parse_float(text: str) -> float:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group(0)) if match else 0.0


def _parse_int(text: str) -> int:
    match = re.search(r"\d+", text or "")
    return int(match.group(0)) if match else 0

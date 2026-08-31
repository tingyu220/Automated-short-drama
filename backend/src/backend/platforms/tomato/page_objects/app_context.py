"""番茄账号渠道与内容应用上下文页面对象。"""
from __future__ import annotations

import re
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError


class AppContextPage:
    """提链前切换并验证番茄应用上下文。"""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def ensure(self, source_entry: str) -> None:
        """确保提链入口对应目标漫剧应用。"""
        app_key = {
            "FREE": "free_comic_app_name",
            "PAID": "paid_comic_app_name",
        }.get(source_entry.upper())
        if app_key is None:
            raise ExternalAdapterError(
                "番茄提链入口类型无效",
                code="TOMATO_CONTEXT_MISMATCH",
                details={"source_entry": source_entry},
            )

        expected_app = self._selectors[app_key]
        expected_channel = self._selectors["expected_channel_name"]
        current = self._read_current()
        if _matches_context(current, expected_app, expected_channel):
            return

        self._page.locator(self._selectors["app_cascader"]).click()
        self._page.wait_for_timeout(800)
        self._click_option(expected_app)
        self._click_option(self._selectors["default_app_name"])
        self._click_option(expected_channel)
        self._page.wait_for_timeout(1500)

        current = self._read_current()
        if not _matches_context(current, expected_app, expected_channel):
            raise ExternalAdapterError(
                "番茄账号渠道或漫剧应用切换失败，已阻断提链",
                code="TOMATO_CONTEXT_MISMATCH",
                details={
                    "expected_app": expected_app,
                    "expected_channel": expected_channel,
                    "actual_context": current,
                },
            )

    def _read_current(self) -> str:
        try:
            value = self._page.locator(
                self._selectors["app_context_value"]
            ).text_content()
        except Exception as exc:
            url = str(getattr(self._page, "url", ""))
            if "/page/home" in url or "/login" in url:
                raise ExternalAdapterError(
                    "番茄登录态已失效，请重新导入登录态",
                    code="TOMATO_LOGIN_REQUIRED",
                    details={"url": url, "reason": "CONTEXT_NOT_AVAILABLE"},
                ) from exc
            raise
        return str(value or "").strip()

    def _click_option(self, text: str) -> None:
        selector = f'{self._selectors["app_option"]}:text-is("{text}")'
        self._page.locator(selector).click()
        self._page.wait_for_timeout(800)


def _matches_context(current: str, expected_app: str, expected_channel: str) -> bool:
    parts = {
        re.sub(r"^(?:应用|渠道)\s*[：:]\s*", "", part.strip())
        for part in re.split(r"[/\n]", current)
        if part.strip()
    }
    labeled_channel = re.search(r"渠道\s*[：:]\s*([^/\n]+)\s*$", current)
    channel = labeled_channel.group(1).strip() if labeled_channel else ""
    channel_matches = channel == expected_channel or expected_channel in parts
    return expected_app in current and channel_matches

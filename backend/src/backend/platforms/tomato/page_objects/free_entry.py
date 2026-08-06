"""番茄免费入口页面对象."""
from __future__ import annotations

from typing import Any


class FreeEntryPage:
    """免费入口操作：搜索剧目、打开详情、生成并读取 IAA 链接."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def search(self, drama_name: str) -> None:
        """进入登录页，搜索剧目并等待结果行出现."""
        self._page.goto(self._selectors["login_url"])
        self._page.locator(self._selectors["search_input"]).fill(drama_name)
        self._page.locator(self._selectors["search_button"]).click()
        self._page.locator(self._selectors["result_row"]).wait_for()

    def open_detail(self) -> None:
        """打开搜索结果中的剧目详情页."""
        self._page.locator(self._selectors["detail_link"]).click()

    def generate_link(self, selected_episode: int) -> None:
        """点击生成按钮，选择指定集数并确认."""
        self._page.locator(self._selectors["generate_button"]).click()
        option = f"{self._selectors['episode_option']}:has-text('第{selected_episode}集')"
        self._page.locator(option).click()
        self._page.locator(self._selectors["confirm_button"]).click()

    def read_link(self) -> str:
        """优先读取输入框值，为空时回退到剪贴板."""
        link_input = self._page.locator(self._selectors["link_input"])
        url = link_input.input_value()
        if url:
            return url
        clipboard = self._page.evaluate("navigator.clipboard.readText()")
        return clipboard if isinstance(clipboard, str) else ""

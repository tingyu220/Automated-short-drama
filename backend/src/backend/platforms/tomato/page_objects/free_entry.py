"""番茄免费入口页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError


class FreeEntryPage:
    """免费入口操作：搜索剧目、打开详情、生成并读取 IAA 链接."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def search(self, drama_name: str) -> None:
        """进入登录页，搜索剧目并等待结果行出现."""
        self._page.goto(
            self._selectors["login_url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )
        self._page.locator(self._selectors["search_input"]).fill(drama_name)
        self._page.locator(self._selectors["search_button"]).click()
        self._page.locator(self._selectors["result_row"]).first.wait_for(
            state="visible", timeout=15000
        )

    def open_detail(self) -> None:
        """打开搜索结果中的剧目详情页."""
        self._page.locator(self._selectors["detail_link"]).click()

    def generate_link(self, selected_episode: int) -> None:
        """点击生成按钮，选择指定集数并确认."""
        self._page.locator(self._selectors["generate_button"]).click()
        self._wait_for_drawer()
        self._open_episode_options()
        options = self._page.locator(self._selectors["episode_option"])
        self._wait_for_options(options)
        texts = options.all_text_contents()
        selected_index = next(
            (
                index
                for index, text in enumerate(texts)
                if _episode_number(text) == selected_episode
            ),
            None,
        )
        if selected_index is None:
            # 先检查禁用选项里有没有——有则说明该集已生成过链接
            disabled_selector = self._selectors.get("episode_option_disabled")
            disabled_options: list[str] = []
            if disabled_selector:
                disabled = self._page.locator(disabled_selector)
                if disabled.count() > 0:
                    disabled_options = [
                        str(text).strip()
                        for text in disabled.all_text_contents()
                    ]
            disabled_numbers = [
                n for text in disabled_options
                if (n := _episode_number(text)) is not None
            ]
            if selected_episode in disabled_numbers:
                raise ExternalAdapterError(
                    "番茄广告起始集数已生成过链接，选项被禁用",
                    code="TOMATO_EPISODE_ALREADY_GENERATED",
                    details={
                        "expected_episode": selected_episode,
                        "available_options": [str(text).strip() for text in texts],
                        "disabled_options": disabled_options,
                    },
                )
            raise ExternalAdapterError(
                "番茄广告起始集数在下拉选项中不存在",
                code="TOMATO_EPISODE_OPTION_MISSING",
                details={
                    "expected_episode": selected_episode,
                    "available_options": [str(text).strip() for text in texts],
                    "disabled_options": disabled_options,
                },
            )
        options.nth(selected_index).click()
        selected_selector = self._selectors.get("episode_selected_value")
        if selected_selector:
            selected_text = self._page.locator(
                selected_selector
            ).text_content()
            if selected_text and _episode_number(selected_text) != selected_episode:
                raise ExternalAdapterError(
                    "番茄广告起始集数未按规则选中，已阻断建链",
                    code="TOMATO_EPISODE_MISMATCH",
                    details={
                        "expected_episode": selected_episode,
                        "actual_value": selected_text,
                    },
                )
        self._page.locator(self._selectors["confirm_button"]).click()
        self._page.wait_for_timeout(3000)

    def count_episodes(self) -> int:
        """打开建链抽屉，按选集下拉最大集数推导总集数。"""
        self._page.locator(self._selectors["generate_button"]).click()
        self._wait_for_drawer()
        self._open_episode_options()
        options = self._page.locator(self._selectors["episode_option"])
        self._wait_for_options(options)
        texts = options.all_text_contents()
        episodes = [
            number for text in texts if (number := _episode_number(text)) is not None
        ]
        return max(episodes, default=1)

    def _wait_for_drawer(self) -> None:
        selector = self._selectors.get("promotion_modal")
        if selector:
            self._page.locator(selector).first.wait_for(
                state="visible", timeout=15000
            )

    def _open_episode_options(self) -> None:
        selector = self._selectors.get("episode_select")
        if selector:
            self._page.locator(selector).click()

    def _wait_for_options(self, options: Any) -> None:
        try:
            options.first.wait_for(state="visible", timeout=10000)
        except Exception as exc:
            all_count = _safe_count(
                self._page,
                self._selectors.get("episode_option_all"),
            )
            disabled_count = _safe_count(
                self._page,
                self._selectors.get("episode_option_disabled"),
            )
            reason = "OPTIONS_NOT_LOADED"
            if all_count is not None and all_count > 0:
                reason = (
                    "ALL_OPTIONS_ALREADY_CREATED"
                    if disabled_count == all_count
                    else "NO_ENABLED_OPTIONS"
                )
            raise ExternalAdapterError(
                "番茄免费建链抽屉未加载可用选集",
                code="TOMATO_EPISODE_OPTIONS_EMPTY",
                details={
                    "selector": self._selectors["episode_option"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "reason": reason,
                    "visible_option_count": all_count,
                    "visible_disabled_option_count": disabled_count,
                },
            ) from exc

    def read_link(self) -> str:
        """优先读取输入框值，超时后回退到 result_link，最后回退到剪贴板."""
        try:
            link_input = self._page.locator(self._selectors["link_input"])
            link_input.wait_for(state="visible", timeout=10000)
            url = link_input.input_value()
            if url:
                return url
        except Exception:
            pass
        result_selector = self._selectors.get("result_link")
        if result_selector:
            try:
                el = self._page.locator(result_selector)
                if el.count() > 0:
                    url = el.text_content()
                    if url and url.strip().startswith("http"):
                        return url.strip()
            except Exception:
                pass
        try:
            clipboard = self._page.evaluate("navigator.clipboard.readText()")
            if isinstance(clipboard, str) and clipboard.strip():
                return clipboard.strip()
        except Exception:
            pass
        return ""


def _safe_count(page: Any, selector: str | None) -> int | None:
    if not selector:
        return None
    try:
        return int(page.locator(selector).count())
    except Exception:
        return None

def _episode_number(text: str) -> int | None:
    digits = "".join(char for char in str(text) if char.isdigit())
    return int(digits) if digits else None

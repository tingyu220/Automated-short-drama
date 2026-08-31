"""番茄真实 Adapter（Playwright 版）单元测试：FakePage 记录调用，不访问真实站点."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest

from backend.domain.errors.domain_error import DramaMismatchError, ExternalAdapterError
from backend.domain.common.timezones import SHANGHAI_TZ
from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.platforms.tomato.tomato_adapter import TomatoAdapter as PlaywrightTomatoAdapter
from backend.platforms.tomato.page_objects.free_entry import FreeEntryPage
from backend.platforms.tomato.page_objects.promotion_link_list import PromotionLinkListPage

TARGET_TIME = datetime(2026, 8, 10, 6, 30, tzinfo=timezone.utc)


SELECTORS = {
    "login_url": "https://tomato.example/login",
    "context_url": "https://tomato.example/page/home?show=true",
    "search_input": "#search-input",
    "search_button": "#search-button",
    "result_row": ".result-row",
    "detail_link": ".detail-link",
    "generate_button": "#generate-button",
    "episode_option": ".episode-option",
    "episode_select": ".episode-select",
    "episode_option_all": ".episode-option-all",
    "episode_option_disabled": ".episode-option-disabled",
    "episode_selected_value": ".episode-selected-value",
    "confirm_button": "#confirm-button",
    "link_input": "#link-input",
    "template_item": ".template-item",
    "template_title": ".template-title",
    "tier_price": ".tier-price",
    "page_order": ".page-order",
    "promotion_modal": ".promotion-modal",
    "promotion_name_input": ".promotion-name-input",
    "template_select_value": ".template-select-value",
    "template_select": ".template-select",
    "template_option": ".template-option",
    "template_option_all": ".template-option-all",
    "template_option_disabled": ".template-option-disabled",
    "result_link": ".result-link",
    "result_drama_name": ".result-drama-name",
    "result_available_time": ".result-available-time",
    "detail_drama_name": ".detail-drama-name",
    "detail_available_time": ".detail-available-time",
    "app_cascader": ".app-cascader",
    "app_context_value": ".app-context-value",
    "app_option": ".app-option",
    "default_app_name": "默认应用",
    "free_comic_app_name": "抖音端原生免费漫剧",
    "paid_comic_app_name": "抖音端原生付费漫剧",
    "expected_channel_name": "李伟",
    "promotion_link_list_url": "https://tomato.example/promotion-links",
    "promotion_link_search_input": "#promotion-link-search",
    "promotion_link_search_type": ".promotion-link-search-type",
    "promotion_link_search_type_name": "漫剧名称",
    "promotion_link_search_button": "#promotion-link-search-button",
    "promotion_link_row": ".promotion-link-row",
    "promotion_link_row_name": ".promotion-link-name",
    "promotion_link_row_identity": ".promotion-link-identity",
    "promotion_link_view_button": ".promotion-link-view",
    "promotion_link_detail": ".promotion-link-detail",
    "promotion_link_detail_container": ".promotion-link-detail-container",
    "promotion_link_close_button": ".promotion-link-close",
}


@dataclass
class FakeLocator:
    """记录单个 locator 上发生的调用."""

    page: "FakePage"
    selector: str
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    value: str = ""
    text: str = ""
    evaluate_all_rows: list[list[str]] = field(default_factory=list)
    evaluate_all_sequence: list[list[list[str]]] = field(default_factory=list)
    all_text_values: list[str] = field(default_factory=list)
    evaluate_results: list[Any] = field(default_factory=list)
    text_sequence: list[str] = field(default_factory=list)
    on_click: Callable[[], None] | None = None
    wait_error: Exception | None = None
    first_access_count: int = 0

    @property
    def first(self) -> "FakeLocator":
        """模拟 Playwright 的 first，测试中仍记录在同一 locator 上。"""
        self.first_access_count += 1
        return self

    def nth(self, index: int) -> "FakeLocator":
        self.calls.append(("nth", (index,), {}))
        return self

    def fill(self, value: str, **kwargs: Any) -> None:
        self.calls.append(("fill", (value,), kwargs))
        self.value = value

    def type(self, value: str, **kwargs: Any) -> None:
        self.calls.append(("type", (value,), kwargs))
        self.value = value

    def press(self, key: str, **kwargs: Any) -> None:
        self.calls.append(("press", (key,), kwargs))

    def click(self, **kwargs: Any) -> None:
        kwargs.pop("timeout", None)
        self.calls.append(("click", (), kwargs))
        if self.on_click is not None:
            self.on_click()

    def wait_for(self, **kwargs: Any) -> None:
        kwargs.pop("timeout", None)
        self.calls.append(("wait_for", (), kwargs))
        if self.wait_error is not None:
            raise self.wait_error

    def input_value(self, **kwargs: Any) -> str:
        self.calls.append(("input_value", (), kwargs))
        return self.value

    def count(self, **kwargs: Any) -> int:
        self.calls.append(("count", (), kwargs))
        return len(self.all_text_values)

    def text_content(self, **kwargs: Any) -> str:
        kwargs.pop("timeout", None)
        self.calls.append(("text_content", (), kwargs))
        if self.text_sequence:
            return self.text_sequence.pop(0)
        return self.text

    def evaluate_all(self, expression: str, arg: Any = None, **kwargs: Any) -> list[Any]:
        self.calls.append(("evaluate_all", (expression,), {"arg": arg, **kwargs}))
        if self.evaluate_all_sequence:
            return list(self.evaluate_all_sequence.pop(0))
        return list(self.evaluate_all_rows)

    def all_text_contents(self, **kwargs: Any) -> list[str]:
        self.calls.append(("all_text_contents", (), kwargs))
        return list(self.all_text_values)

    def evaluate(self, expression: str, arg: Any = None, **kwargs: Any) -> Any:
        self.calls.append(("evaluate", (expression,), {"arg": arg, **kwargs}))
        return self.evaluate_results.pop(0) if self.evaluate_results else None

    def locator(self, selector: str, **kwargs: Any) -> "FakeLocator":
        """模拟在 locator 内继续查找子 locator（测试中返回自身）。"""
        self.calls.append(("locator", (selector,), kwargs))
        return self

    def inner_html(self, **kwargs: Any) -> str:
        self.calls.append(("inner_html", (), kwargs))
        return self.text


class FakePage:
    """Playwright Page 最小 fake：按 selector 返回 FakeLocator，记录全部调用."""

    def __init__(self) -> None:
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.text_locators: dict[str, FakeLocator] = {}
        self.clipboard_text = ""
        self.evaluate_result: Any = None
        self.screenshot_calls: list[dict[str, Any]] = []
        self.screenshot_error: Exception | None = None
        self.selected_app = ""
        self.url = ""
        self.set_text(SELECTORS["app_context_value"], "")

    def goto(self, url: str, **kwargs: Any) -> None:
        kwargs.pop("wait_until", None)
        kwargs.pop("timeout", None)
        self.calls.append(("goto", (url,), kwargs))
        self.url = url

    def wait_for_load_state(self, state: str, **kwargs: Any) -> None:
        self.calls.append(("wait_for_load_state", (state,), kwargs))

    def wait_for_selector(self, selector: str, **kwargs: Any) -> None:
        self.calls.append(("wait_for_selector", (selector,), kwargs))
        loc = self.locator(selector)
        loc.wait_for(**kwargs)

    def locator(self, selector: str, **kwargs: Any) -> FakeLocator:
        self.calls.append(("locator", (selector,), kwargs))
        option_prefix = SELECTORS["app_option"] + ':text-is("'
        if selector.startswith(option_prefix) and selector.endswith('")'):
            text = selector[len(option_prefix) : -2]
            return self.get_by_text(text, exact=True)
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
            if selector == SELECTORS["episode_option"]:
                self.locators[selector].all_text_values = ["1集"]
            if selector == SELECTORS["template_option"]:
                self.locators[selector].all_text_values = ["9.9 档模板"]
        return self.locators[selector]

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.calls.append(("wait_for_timeout", (milliseconds,), {}))

    def get_by_text(self, text: str, **kwargs: Any) -> FakeLocator:
        self.calls.append(("get_by_text", (text,), kwargs))
        if text not in self.text_locators:
            self.text_locators[text] = FakeLocator(page=self, selector=text)
        if text in {
            SELECTORS["free_comic_app_name"],
            SELECTORS["paid_comic_app_name"],
        }:
            self.text_locators[text].on_click = lambda: setattr(
                self, "selected_app", text
            )
        if text == SELECTORS["expected_channel_name"]:
            self.text_locators[text].on_click = lambda: self.set_text(
                SELECTORS["app_context_value"],
                f"{self.selected_app} / {SELECTORS['default_app_name']} / {text}",
            )
        return self.text_locators[text]

    def evaluate(self, expression: str, arg: Any = None, **kwargs: Any) -> Any:
        self.calls.append(("evaluate", (expression, arg), kwargs))
        return self.evaluate_result

    def set_value(self, selector: str, value: str) -> None:
        """预置 locator 输入值，不产生调用记录."""
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        self.locators[selector].value = value

    def set_text(self, selector: str, value: str) -> None:
        """预置文本，不产生调用记录。"""
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        self.locators[selector].text = value

    def screenshot(self, **kwargs: Any) -> None:
        self.screenshot_calls.append(kwargs)
        if self.screenshot_error is not None:
            raise self.screenshot_error


def configure_drama_candidates(
    page: FakePage,
    rows: list[list[str]],
    *,
    detail_name: str = "剧A",
    detail_time: str = "2026-08-10 14:30",
) -> None:
    """配置完整候选结构；仅浏览器 Page 作为外部边界使用 fake。"""
    page.locator(SELECTORS["result_row"]).evaluate_all_rows = rows
    page.text_locators[detail_name] = FakeLocator(
        page=page,
        selector=detail_name,
        text=detail_name,
    )
    page.set_text(SELECTORS["detail_drama_name"], detail_name)
    page.set_text(SELECTORS["detail_available_time"], detail_time)


def make_adapter(
    page: FakePage | None = None,
    dry_run: bool = True,
    artifact_dir: Path | None = None,
):
    return PlaywrightTomatoAdapter(
        selectors=dict(SELECTORS),
        page=page or FakePage(),
        dry_run=dry_run,
        artifact_dir=artifact_dir,
    )


class TestFreeEntrySearch:
    """免费入口搜索流程顺序与参数验证."""

    def test_extract_iaa_link_search_flow(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-3")
        page.locator(SELECTORS["episode_option"]).all_text_values = [
            "第1集",
            "第2集",
            "第3集",
        ]
        adapter = make_adapter(page=page, dry_run=False)

        link = adapter.extract_iaa_link("剧A", TARGET_TIME, 60, 3)

        assert isinstance(link, PromotionLink)
        assert link.promotion_url == "https://tomato.example/iaa/ep-3"
        assert link.source_platform == "TOMATO"
        assert link.source_entry == "FREE"
        assert link.acquisition_method == "PAGE_EXTRACTION"
        assert link.link_type == "IAA"
        assert ("goto", (SELECTORS["login_url"],), {}) in page.calls
        search_input_calls = page.locators[SELECTORS["search_input"]].calls
        assert ("wait_for", (), {"state": "visible"}) in search_input_calls
        assert ("click", (), {}) in search_input_calls
        assert ("type", ("剧A",), {"delay": 50}) in search_input_calls
        assert ("press", ("Enter",), {}) in search_input_calls
        assert ("type", ("剧A",), {"delay": 50}) in search_input_calls
        result_calls = page.locators[SELECTORS["result_row"]].calls
        assert "evaluate_all" in [call[0] for call in result_calls]
        detail_selector = f'{SELECTORS["detail_link"]}[href="/detail/right"]'
        assert page.locators[detail_selector].calls == [
            ("click", (), {}),
        ]
        assert page.locators[SELECTORS["generate_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["episode_option"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("all_text_contents", (), {}),
            ("nth", (2,), {}),
            ("click", (), {}),
        ]
        assert page.locators[SELECTORS["confirm_button"]].calls == [("click", (), {})]
        assert page.locators[SELECTORS["link_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("input_value", (), {}),
        ]
        assert SELECTORS["free_comic_app_name"] in page.locators[
            SELECTORS["app_context_value"]
        ].text
        assert page.locators[SELECTORS["episode_select"]].calls == [
            ("click", (), {})
        ]

    def test_switches_context_on_home_before_opening_drama_list(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        # 忽略 fixture 预置 locator，只验证实际提链调用的导航顺序。
        page.calls.clear()

        make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        # 验证推广链列表搜索优先于免费入口剧目列表
        first_promotion_search_index = next(
            index
            for index, call in enumerate(page.calls)
            if call == ("goto", (SELECTORS["promotion_link_list_url"],), {})
        )
        first_list_index = next(
            index
            for index, call in enumerate(page.calls)
            if call == ("goto", (SELECTORS["login_url"],), {})
        )
        assert first_promotion_search_index < first_list_index
        context_click_index = next(
            index
            for index, call in enumerate(page.calls)
            if call[0] == "locator" and call[1] == (SELECTORS["app_cascader"],)
        )
        assert context_click_index < first_list_index

    def test_retries_until_async_search_rows_have_time(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        rows = page.locator(SELECTORS["result_row"])
        rows.evaluate_all_sequence = [
            [["剧A", "-", "/detail/right", 0]],
            [["剧A", "2026-08-10 14:30", "/detail/right", 0]],
        ]
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-1")

        link = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        assert link.promotion_url.endswith("ep-1")
        assert sum(call[0] == "evaluate_all" for call in rows.calls) >= 2

    def test_unique_exact_title_can_use_detail_when_list_time_is_unavailable(self):
        """番茄列表长期显示“-”时，唯一同名候选仍应进入详情复核。"""
        page = FakePage()
        configure_drama_candidates(
            page,
            [["剧A", "-", "/detail/right"]],
            detail_time="2026-08-10 14:30",
        )
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-1")

        link = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        assert link.promotion_url.endswith("ep-1")
        assert sum(
            call[0] == "evaluate_all"
            for call in page.locators[SELECTORS["result_row"]].calls
        ) == 3
        detail_selector = f'{SELECTORS["detail_link"]}[href="/detail/right"]'
        assert page.locators[detail_selector].calls == [
            ("click", (), {}),
        ]

    def test_missing_episode_option_rechecks_promotion_links_before_failing(
        self, monkeypatch
    ):
        """目标集数不可选时，必须回推广链列表复用已创建链接。"""
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-1")
        calls = iter([None, "https://tomato.example/iaa/existing-ep-1"])
        monkeypatch.setattr(
            PromotionLinkListPage,
            "find_iaa",
            lambda self, drama_name, episode: next(calls),
        )
        monkeypatch.setattr(
            PromotionLinkListPage, "find_existing", lambda *args: None
        )
        monkeypatch.setattr(
            FreeEntryPage,
            "generate_link",
            lambda *args: (_ for _ in ()).throw(
                ExternalAdapterError(
                    "目标集数不存在",
                    code="TOMATO_EPISODE_OPTION_MISSING",
                )
            ),
        )

        link = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        assert link.promotion_url.endswith("existing-ep-1")

    def test_lookup_miss_returns_to_detail_before_generating(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-1")

        make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        promotion_index = next(
            index
            for index, call in enumerate(page.calls)
            if call == ("goto", (SELECTORS["promotion_link_list_url"],), {})
        )
        detail_index = next(
            index
            for index, call in enumerate(page.calls[promotion_index + 1 :], promotion_index + 1)
            if call == ("goto", (SELECTORS["login_url"],), {})
        )
        generate_index = next(
            index
            for index, call in enumerate(page.calls)
            if call == ("locator", (SELECTORS["generate_button"],), {})
        )
        assert detail_index < generate_index

    def test_waits_on_first_result_row_when_search_returns_multiple_rows(self):
        page = FakePage()
        configure_drama_candidates(
            page,
            [
                ["剧A", "2026-08-10 14:30", "/detail/right"],
                ["剧A", "2026-08-10 14:31", "/detail/other"],
            ],
        )

        count = make_adapter(page=page, dry_run=False).get_episode_count(
            "剧A", TARGET_TIME
        )

        assert count is not None
        # 验证搜索结果行被正确读取
        result_calls = page.locators[SELECTORS["result_row"]].calls
        assert any(call[0] == "evaluate_all" for call in result_calls)

    def test_read_link_falls_back_to_clipboard_when_input_empty(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.clipboard_text = "https://tomato.example/iaa/clipboard"
        page.evaluate_result = page.clipboard_text
        page.set_value(SELECTORS["link_input"], "")
        adapter = make_adapter(page=page, dry_run=False)

        link = adapter.extract_iaa_link("剧A", TARGET_TIME, 40, 1)

        assert link.promotion_url == "https://tomato.example/iaa/clipboard"
        assert page.locators[SELECTORS["link_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("input_value", (), {}),
        ]
        assert any(
            name == "evaluate" and "readText" in expression[0]
            for name, expression, _ in page.calls
        )

    def test_read_link_returns_empty_when_clipboard_evaluate_is_none(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.evaluate_result = None
        page.set_value(SELECTORS["link_input"], "")
        adapter = make_adapter(page=page, dry_run=False)

        link = adapter.extract_iaa_link("剧A", TARGET_TIME, 40, 1)

        assert link.promotion_url == ""
        assert any(
            name == "evaluate" and "readText" in expression[0]
            for name, expression, _ in page.calls
        )

    def test_episode_selection_mismatch_never_confirms(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.set_text(SELECTORS["episode_selected_value"], "4集")

        with pytest.raises(Exception, match="起始集数"):
            make_adapter(page=page, dry_run=False).extract_iaa_link(
                "剧A", TARGET_TIME, 60, 2
            )

        assert page.locators.get(SELECTORS["confirm_button"]) is None

    def test_episode_selection_accepts_chinese_prefix_and_spacing(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["episode_option"]).all_text_values = [
            "第1集",
            " 2 集 ",
        ]
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-1")

        make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 2
        )

        assert page.locators[SELECTORS["episode_option"]].calls[-2:] == [
            ("nth", (1,), {}),
            ("click", (), {}),
        ]

    def test_empty_episode_options_raise_diagnostic_error(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["episode_option"]).wait_error = RuntimeError(
            "options are not visible"
        )

        with pytest.raises(ExternalAdapterError) as caught:
            make_adapter(page=page, dry_run=False).extract_iaa_link(
                "剧A", TARGET_TIME, 40, 1
            )

        assert caught.value.code == "TOMATO_EPISODE_OPTIONS_EMPTY"
        assert caught.value.details["error_type"] == "RuntimeError"

    def test_get_episode_count_reads_max_episode_option(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["episode_option"]).all_text_values = [
            "1集",
            "2集",
            "51集",
        ]

        count = make_adapter(page=page, dry_run=False).get_episode_count(
            "剧A", TARGET_TIME
        )

        assert count == 51
        assert page.locators[SELECTORS["generate_button"]].calls == [
            ("click", (), {})
        ]


class TestPaidEntry:
    """付费入口模板扫描与链接生成验证."""

    def test_scan_iap_templates_returns_price_and_page_order(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_item"]).evaluate_all_rows = [
            ["2.9 档模板", "2.9", "1"],
            ["9.9 档模板", "9.9", "2"],
        ]
        adapter = make_adapter(page=page, dry_run=False)

        templates = adapter.scan_iap_templates("剧A", TARGET_TIME)

        assert templates == [
            TemplateInfo(
                template_id="2.9 档模板",
                drama_name="剧A",
                title="2.9 档模板",
                price=2.9,
                page_order=1,
            ),
            TemplateInfo(
                template_id="9.9 档模板",
                drama_name="剧A",
                title="9.9 档模板",
                price=9.9,
                page_order=2,
            ),
        ]
        item_locator = page.locators[SELECTORS["template_item"]]
        assert item_locator.calls[0][0] == "count"
        assert item_locator.calls[1][0] == "evaluate_all"
        expression = item_locator.calls[1][1][0]
        assert "querySelector" in expression
        arg = item_locator.calls[1][2]["arg"]
        assert arg["template_title"] == SELECTORS["template_title"]
        assert arg["tier_price"] == SELECTORS["tier_price"]
        assert arg["page_order"] == SELECTORS["page_order"]
        assert SELECTORS["paid_comic_app_name"] in page.locators[
            SELECTORS["app_context_value"]
        ].text

    def test_scan_real_modal_templates_uses_only_first_tier_price(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_option"]).all_text_values = [
            "小额",
            "超小额",
        ]
        page.locator(SELECTORS["promotion_modal"]).evaluate_results = [
            [12.39, 11.25, 8.32, 3.96],
            [7.08, 2.7, 1.8, 1.5],
        ]

        templates = make_adapter(page=page, dry_run=False).scan_iap_templates(
            "剧A", TARGET_TIME
        )

        assert [(item.title, item.price) for item in templates] == [
            ("小额", 12.39),
            ("超小额", 7.08),
        ]

    def test_scan_then_generate_iap_link_closed_loop(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_item"]).evaluate_all_rows = [
            ["9.9 档模板", "9.9", "2"],
        ]
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iap/9-9")
        adapter = make_adapter(page=page, dry_run=False)

        templates = adapter.scan_iap_templates("剧A", TARGET_TIME)
        link = adapter.generate_iap_link("剧A", TARGET_TIME, templates[0])

        assert templates[0].title == "9.9 档模板"
        assert templates[0].template_id == "9.9 档模板"
        assert page.locators[SELECTORS["template_option"]].calls[-2:] == [
            ("nth", (0,), {}),
            ("click", (), {}),
        ]
        assert link.promotion_url == "https://tomato.example/iap/9-9"

    def test_generate_iap_link_clicks_template_and_reads_link(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["link_input"]).value = "https://tomato.example/iap/9-9"
        adapter = make_adapter(page=page, dry_run=False)
        template = TemplateInfo(
            template_id="tpl-9-9",
            drama_name="剧A",
            title="9.9 档模板",
            price=9.9,
            page_order=2,
        )

        link = adapter.generate_iap_link("剧A", TARGET_TIME, template)

        assert isinstance(link, PromotionLink)
        assert link.promotion_url == "https://tomato.example/iap/9-9"
        assert link.source_platform == "TOMATO"
        assert link.source_entry == "PAID"
        assert link.acquisition_method == "PAGE_EXTRACTION"
        assert link.link_type == "IAP"
        assert page.locators[SELECTORS["template_option"]].calls[-2:] == [
            ("nth", (0,), {}),
            ("click", (), {}),
        ]
        assert page.locators[SELECTORS["generate_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["confirm_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["link_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("input_value", (), {}),
        ]

    def test_generate_real_modal_template_reads_aweme_link_from_drawer(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.set_text(
            SELECTORS["result_link"],
            "aweme://playlet?playlet_id=real-test",
        )
        page.locator(SELECTORS["result_link"]).all_text_values = [""]
        page.locator(SELECTORS["template_option"]).all_text_values = ["小额"]
        adapter = make_adapter(page=page, dry_run=False)
        template = TemplateInfo(
            template_id="小额",
            drama_name="剧A",
            title="小额",
            price=11.25,
            page_order=1,
        )

        link = adapter.generate_iap_link("剧A", TARGET_TIME, template)

        assert link.promotion_url == (
            "aweme://playlet?playlet_id=real-test"
        )

    def test_generate_iap_link_selects_template_inside_opened_drawer(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_option"]).all_text_values = [
            "小额（30-60集）",
            "超小额（60集以上）",
        ]
        page.set_text(
            SELECTORS["result_link"],
            "aweme://playlet?playlet_id=real-template",
        )
        page.locator(SELECTORS["result_link"]).all_text_values = [""]
        template = TemplateInfo(
            template_id="超小额（60集以上）",
            drama_name="剧A",
            title="超小额（60集以上）",
            price=2.9,
            page_order=2,
        )

        link = make_adapter(page=page, dry_run=False).generate_iap_link(
            "剧A", TARGET_TIME, template
        )

        assert link.promotion_url == "aweme://playlet?playlet_id=real-template"
        assert page.locators[SELECTORS["template_select"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["promotion_modal"]].first_access_count == 1
        assert page.locators[SELECTORS["template_option"]].calls[-2:] == [
            ("nth", (1,), {}),
            ("click", (), {}),
        ]
        assert page.locators[SELECTORS["generate_button"]].calls == [
            ("click", (), {}),
        ]
        assert page.locators[SELECTORS["confirm_button"]].calls == [
            ("click", (), {})
        ]
        assert "超小额（60集以上）" not in page.text_locators

    def test_empty_template_options_raise_diagnostic_error(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_option"]).wait_error = RuntimeError(
            "options are not visible"
        )
        template = TemplateInfo(
            template_id="tpl-9-9",
            drama_name="剧A",
            title="9.9 档模板",
            price=9.9,
            page_order=1,
        )

        with pytest.raises(ExternalAdapterError) as caught:
            make_adapter(page=page, dry_run=False).generate_iap_link(
                "剧A", TARGET_TIME, template
            )

        assert caught.value.code == "TOMATO_TEMPLATE_OPTIONS_EMPTY"
        assert caught.value.details["error_type"] == "RuntimeError"

    def test_generate_iap_link_clipboard_none_returns_empty(self):
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.evaluate_result = None
        page.set_value(SELECTORS["link_input"], "")
        adapter = make_adapter(page=page, dry_run=False)
        template = TemplateInfo(
            template_id="tpl-9-9",
            drama_name="剧A",
            title="9.9 档模板",
            price=9.9,
            page_order=2,
        )

        link = adapter.generate_iap_link("剧A", TARGET_TIME, template)

        assert link.promotion_url == ""
        assert any(
            name == "evaluate" and "readText" in expression[0]
            for name, expression, _ in page.calls
        )


class TestZeroPriceFallback:
    """推广链列表优先搜索：命中两档时跳过 PAID 入口模板扫描。"""

    def test_zero_price_falls_back_to_list_iap_and_cache_prevents_link_confusion(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_item"]).evaluate_all_rows = [
            ["模板A", "", ""],
            ["模板B", "", ""],
        ]
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "模板A", 0, "剧A 模板A 用户支付金额 2.9元"],
            ["剧A", "模板B", 1, "剧A 模板B 用户支付金额 9.9元"],
        ]
        page.locator(SELECTORS["promotion_link_detail"]).text_sequence = [
            "aweme://playlet?playlet_id=iap-2-9",
            "aweme://playlet?playlet_id=iap-9-9",
        ]
        page.locator(SELECTORS["promotion_link_detail_container"]).text_sequence = [
            "用户支付金额 2.9元 推广链接",
            "用户支付金额 9.9元 推广链接",
        ]

        adapter = make_adapter(page=page, dry_run=False)
        templates = adapter.scan_iap_templates("剧A", TARGET_TIME)

        assert len(templates) == 2
        assert templates[0].price == 2.9
        assert templates[1].price == 9.9
        assert templates[0].page_order == 1
        assert templates[1].page_order == 2

        link_2_9 = adapter.generate_iap_link("剧A", TARGET_TIME, templates[0])
        link_9_9 = adapter.generate_iap_link("剧A", TARGET_TIME, templates[1])

        assert link_2_9.promotion_url == "aweme://playlet?playlet_id=iap-2-9"
        assert link_9_9.promotion_url == "aweme://playlet?playlet_id=iap-9-9"
        assert link_2_9.promotion_url != link_9_9.promotion_url

    def test_promotion_list_first_skips_paid_entry_when_both_found(self) -> None:
        """推广链列表命中2.9和9.9两档时，不进入付费入口扫描模板。"""
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "模板A", 0, "剧A 模板A 用户支付金额 2.9元"],
            ["剧A", "模板B", 1, "剧A 模板B 用户支付金额 9.9元"],
        ]
        page.locator(SELECTORS["promotion_link_detail"]).text_sequence = [
            "aweme://playlet?playlet_id=iap-2-9",
            "aweme://playlet?playlet_id=iap-9-9",
        ]
        page.locator(SELECTORS["promotion_link_detail_container"]).text_sequence = [
            "用户支付金额 2.9元 推广链接",
            "用户支付金额 9.9元 推广链接",
        ]

        adapter = make_adapter(page=page, dry_run=False)
        templates = adapter.scan_iap_templates("剧A", TARGET_TIME)

        assert len(templates) == 2
        assert templates[0].price == 2.9
        assert templates[1].price == 9.9
        template_item = page.locators.get(SELECTORS["template_item"])
        assert template_item is None or not template_item.calls

    def test_promotion_list_partial_falls_through_to_paid_scan(self) -> None:
        """推广链列表只命中2.9档时，仍进入付费入口扫描9.9模板。"""
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["template_item"]).evaluate_all_rows = [
            ["9.9 档模板", "9.9", "2"],
        ]
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "模板A", 0, "剧A 模板A 用户支付金额 2.9元"],
        ]
        page.locator(SELECTORS["promotion_link_detail"]).text_sequence = [
            "aweme://playlet?playlet_id=iap-2-9",
        ]
        page.locator(SELECTORS["promotion_link_detail_container"]).text_sequence = [
            "用户支付金额 2.9元 推广链接",
        ]

        adapter = make_adapter(page=page, dry_run=False)
        templates = adapter.scan_iap_templates("剧A", TARGET_TIME)

        prices = sorted(t.price for t in templates)
        assert 2.9 in prices
        assert 9.9 in prices
        template_item = page.locators.get(SELECTORS["template_item"])
        assert template_item is not None
        assert any(call[0] == "evaluate_all" for call in template_item.calls)


class TestExistingPromotionLinkReuse:
    """已生成的模板/选集链接必须查看复用，禁止再次创建。"""

    def test_existing_iaa_episode_link_is_viewed_without_generate(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "3集", 0]
        ]
        page.set_text(
            SELECTORS["promotion_link_detail"],
            "aweme://playlet?playlet_id=existing-iaa",
        )

        link = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 60, 3
        )

        assert link.promotion_url == (
            "aweme://playlet?playlet_id=existing-iaa"
        )
        assert page.locators.get(SELECTORS["generate_button"]) is None
        assert page.locators[SELECTORS["promotion_link_search_type"]].calls == [
            ("nth", (0,), {}),
            ("wait_for", (), {"state": "visible"}),
            ("click", (), {}),
            ("nth", (0,), {}),
            ("wait_for", (), {"state": "visible"}),
            ("click", (), {}),
        ]
        # 验证通过行内定位点击"查看"按钮（不再使用 :nth-match 全局选择）
        row_locator = page.locators[SELECTORS["promotion_link_row"]]
        row_calls = row_locator.calls
        assert ("nth", (0,), {}) in row_calls
        assert ("locator", ("button:has-text('查看')",), {}) in row_calls
        assert ("click", (), {}) in row_calls

    def test_existing_iap_template_link_is_viewed_without_generate(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "9.9 档模板", 0]
        ]
        page.set_text(
            SELECTORS["promotion_link_detail"],
            "aweme://playlet?playlet_id=existing-iap",
        )
        template = TemplateInfo(
            template_id="tpl-9-9",
            drama_name="剧A",
            title="9.9 档模板",
            price=9.9,
            page_order=2,
        )

        link = make_adapter(page=page, dry_run=False).generate_iap_link(
            "剧A", TARGET_TIME, template
        )

        assert link.promotion_url == (
            "aweme://playlet?playlet_id=existing-iap"
        )
        assert page.locators.get(SELECTORS["generate_button"]) is None

    def test_existing_iaa_disabled_episode_is_reused_from_row_text(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "2026-08-19", 0, "剧A 广告起始集数 第2集"]
        ]
        page.set_text(
            SELECTORS["promotion_link_detail"],
            "aweme://playlet?playlet_id=existing-iaa-2",
        )
        page.set_text(
            SELECTORS["promotion_link_detail_container"],
            "广告起始集数 第2集 推广链接",
        )

        link = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 60, 2
        )

        assert link.promotion_url.endswith("existing-iaa-2")
        assert page.locators.get(SELECTORS["generate_button"]) is None

    def test_disabled_episode_falls_back_to_promotion_list(self) -> None:
        """目标集数在下拉中被禁用（已生成过链接），应通过推广链接列表复用。"""
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        # 可用选项里没有第1集，但禁用选项里有
        page.locator(SELECTORS["episode_option"]).all_text_values = ["第2集", "第3集"]
        page.locator(SELECTORS["episode_option_disabled"]).all_text_values = ["第1集"]
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "1集", 0, "剧A 广告起始集数 第1集"]
        ]
        page.set_text(
            SELECTORS["promotion_link_detail"],
            "aweme://playlet?playlet_id=existing-iaa-1",
        )
        page.set_text(
            SELECTORS["promotion_link_detail_container"],
            "广告起始集数 第1集 推广链接",
        )

        link = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 60, 1
        )

        assert link.promotion_url.endswith("existing-iaa-1")
        assert link.acquisition_method == "PROMOTION_LIST_VIEW"

    def test_existing_iap_disabled_template_reuses_first_matching_price(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "超超小额", 0, "剧A 充值面板 超超小额"]
        ]
        page.set_text(
            SELECTORS["promotion_link_detail"],
            "aweme://playlet?playlet_id=existing-iap-99",
        )
        page.set_text(
            SELECTORS["promotion_link_detail_container"],
            "档位1 用户支付金额 8.3元 推广链接",
        )
        template = TemplateInfo(
            template_id="tpl-9-9",
            drama_name="剧A",
            title="9.9 档模板",
            price=9.9,
            page_order=1,
        )

        link = make_adapter(page=page, dry_run=False).generate_iap_link(
            "剧A", TARGET_TIME, template
        )

        assert link.promotion_url.endswith("existing-iap-99")
        assert page.locators.get(SELECTORS["generate_button"]) is None

    def test_episode_count_falls_back_to_promotion_list_total(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["episode_option"]).wait_error = RuntimeError(
            "all existing episodes are disabled"
        )
        page.locator(SELECTORS["episode_option_all"]).all_text_values = ["第1集"]
        page.locator(SELECTORS["episode_option_disabled"]).all_text_values = ["第1集"]
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "", 0, "剧A 总集数：84集 广告起始集数 第2集"]
        ]

        count = make_adapter(page=page, dry_run=False).get_episode_count(
            "剧A", TARGET_TIME
        )

        assert count == 84

    def test_multiple_exact_links_take_first_without_generate(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page, [["剧A", "2026-08-10 14:30", "/detail/right"]]
        )
        page.locator(SELECTORS["promotion_link_row"]).evaluate_all_rows = [
            ["剧A", "1集", 0],
            ["剧A", "1集", 1],
        ]
        page.set_text(
            SELECTORS["promotion_link_detail"],
            "aweme://playlet?playlet_id=existing-iaa",
        )

        result = make_adapter(page=page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        assert result.promotion_url == (
            "aweme://playlet?playlet_id=existing-iaa"
        )
        assert page.locators.get(SELECTORS["generate_button"]) is None


class TestDryRun:
    """dry_run=True 只记录调用，不操作 page."""

    def test_dry_run_never_touches_page(self):
        page = FakePage()
        adapter = make_adapter(page=page, dry_run=True)

        adapter.extract_iaa_link("剧A", TARGET_TIME, 60, 3)
        adapter.scan_iap_templates("剧A", TARGET_TIME)
        adapter.generate_iap_link(
            "剧A",
            TARGET_TIME,
            TemplateInfo(
                template_id="tpl-9-9",
                drama_name="剧A",
                title="9.9 档模板",
                price=9.9,
                page_order=2,
            ),
        )

        assert page.calls == []
        assert [call[0] for call in adapter.recorded_calls] == [
            "extract_iaa_link",
            "scan_iap_templates",
            "generate_iap_link",
        ]

    def test_default_selectors_json_has_all_required_keys(self):
        config_path = (
            Path(__file__).resolve().parents[3]
            / "configs"
            / "defaults"
            / "tomato_selectors.json"
        )
        required_keys = {
            "login_url",
            "search_input",
            "search_button",
            "result_row",
            "result_drama_name",
            "result_available_time",
            "detail_link",
            "detail_available_time",
            "generate_button",
            "episode_option",
            "confirm_button",
            "link_input",
            "template_item",
            "tier_price",
            "page_order",
            "promotion_link_list_url",
            "promotion_link_search_input",
            "promotion_link_search_button",
            "promotion_link_row",
            "promotion_link_row_name",
            "promotion_link_row_identity",
            "promotion_link_view_button",
            "promotion_link_detail",
        }
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert required_keys <= data.keys()

    def test_adapter_loads_default_selectors_from_repo_config(self):
        adapter = PlaywrightTomatoAdapter(page=None, dry_run=True)
        assert adapter._selectors["login_url"]
        assert adapter._selectors["template_item"]

    def test_default_selectors_match_verified_tomato_list_dom(self):
        """生产默认值必须对应核验过的真实页面 DOM 结构（Arco Design 表格）。"""
        adapter = PlaywrightTomatoAdapter(page=None, dry_run=True)

        assert adapter._selectors["login_url"].endswith(
            "/sale/short-play/list"
        )
        assert adapter._selectors["promotion_link_list_url"].endswith(
            "/sale/short-play/promotion-list"
        )
        assert adapter._selectors["search_input"] == "#query_input"
        assert adapter._selectors["result_row"] == (
            "tbody tr.arco-table-tr"
        )
        assert adapter._selectors["result_drama_name"] == (
            ".book_name_content"
        )
        assert adapter._selectors["result_available_time"] == (
            "td:nth-child(8) .arco-table-cell-wrap-value"
        )
        assert adapter._selectors["detail_link"] == (
            "a.e2e-list-table-book-link"
        )
        assert adapter._selectors["detail_available_time"] == (
            'span:has-text("预估投放时间:") + span'
        )
        assert adapter._selectors["expected_channel_name"] == "李伟"
        assert adapter._selectors["generate_button"] == (
            "button:has-text('获取漫剧推广链')"
        )
        assert adapter._selectors["promotion_link_row"] == (
            "tbody tr.arco-table-tr"
        )

    def test_default_selectors_only_match_visible_select_options(self):
        """Arco 会保留隐藏下拉节点，选项选择器不能让隐藏节点排在 first。"""
        adapter = PlaywrightTomatoAdapter(page=None, dry_run=True)

        assert ":visible" in adapter._selectors["episode_option"]
        assert ":visible" in adapter._selectors["template_option"]

    def test_adapter_satisfies_protocol(self):
        assert isinstance(make_adapter(), TomatoAdapter)


class TestSameNameDramaSelection:
    """同名剧必须列表唯一命中，并在详情页再次核对。"""

    def test_iaa_selects_exact_minute_href_instead_of_first_row(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page,
            [
                ["剧A", "2026-08-10 14:29", "/detail/old"],
                ["剧A", "2026-08-10 14:30:45", "/detail/right"],
            ],
        )
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa")

        make_adapter(page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        assert page.locators[
            f'{SELECTORS["detail_link"]}[href="/detail/right"]'
        ].calls == [("click", (), {})]
        assert page.locators[SELECTORS["generate_button"]].calls == [
            ("click", (), {})
        ]

    def test_detail_name_uses_exact_expected_text_not_hashed_css(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page,
            [["剧A", "2026-08-10 14:30", "/detail/right"]],
            detail_name="页面中不存在该旧选择器",
        )
        page.text_locators["剧A"] = FakeLocator(
            page=page,
            selector="剧A",
            text="剧A",
        )
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa")

        make_adapter(page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1
        )

        assert page.text_locators["剧A"].calls == [
            ("text_content", (), {}),
        ]

    @pytest.mark.parametrize(
        ("detail_name", "detail_time"),
        [("另一部剧", "2026-08-10 14:30"), ("剧A", "2026-08-10 14:36")],
    )
    def test_detail_mismatch_never_clicks_generate(
        self, detail_name: str, detail_time: str
    ) -> None:
        page = FakePage()
        configure_drama_candidates(
            page,
            [["剧A", "2026-08-10 14:30", "/detail/right"]],
            detail_name=detail_name,
            detail_time=detail_time,
        )

        with pytest.raises(DramaMismatchError) as caught:
            make_adapter(page, dry_run=False).extract_iaa_link(
                "剧A", TARGET_TIME, 40, 1
            )

        assert caught.value.code == "DRAMA_MISMATCH"
        assert caught.value.details["stage"] == "DETAIL"
        assert page.locators.get(SELECTORS["generate_button"]) is None

    def test_multiple_list_matches_never_open_detail_or_generate(self) -> None:
        page = FakePage()
        configure_drama_candidates(
            page,
            [
                ["剧A", "2026-08-10 14:30", "/detail/one"],
                ["剧A", "2026-08-10 14:30", "/detail/two"],
            ],
        )

        with pytest.raises(DramaMismatchError) as caught:
            make_adapter(page, dry_run=False).extract_iaa_link(
                "剧A", TARGET_TIME, 40, 1
            )

        assert caught.value.details["stage"] == "LIST"
        assert not any("/detail/" in selector for selector in page.locators)
        assert page.locators.get(SELECTORS["generate_button"]) is None

    def test_confirmed_candidate_is_reused_without_time_window_selection(self) -> None:
        """人工确认后按定位复用候选，不重新按时间窗口猜测。"""
        page = FakePage()
        configure_drama_candidates(
            page,
            [["剧A", "2026-08-10 14:30", "/detail/confirmed"]],
        )
        confirmation = ConfirmedDramaMatch(
            locator_key="/detail/confirmed",
            available_minute=datetime(
                2026, 8, 10, 14, 30, tzinfo=SHANGHAI_TZ
            ),
            confirmed_at=datetime(2026, 8, 10, 6, 40, tzinfo=timezone.utc),
        )

        make_adapter(page, dry_run=False).extract_iaa_link(
            "剧A", TARGET_TIME, 40, 1, confirmation
        )

        assert page.locators[
            f'{SELECTORS["detail_link"]}[href="/detail/confirmed"]'
        ].calls == [("click", (), {})]

    def test_changed_confirmed_candidate_is_rejected(self) -> None:
        """确认候选时间变化时不能静默改选或继续生成。"""
        page = FakePage()
        configure_drama_candidates(
            page,
            [["剧A", "2026-08-10 14:31", "/detail/confirmed"]],
        )
        confirmation = ConfirmedDramaMatch(
            locator_key="/detail/confirmed",
            available_minute=datetime(
                2026, 8, 10, 14, 30, tzinfo=SHANGHAI_TZ
            ),
            confirmed_at=datetime(2026, 8, 10, 6, 40, tzinfo=timezone.utc),
        )

        with pytest.raises(DramaMismatchError) as caught:
            make_adapter(page, dry_run=False).extract_iaa_link(
                "剧A", TARGET_TIME, 40, 1, confirmation
            )

        assert caught.value.details["reason"] == "CONFIRMED_CANDIDATE_CHANGED"
        assert page.locators.get(SELECTORS["generate_button"]) is None

    def test_screenshot_failure_does_not_hide_drama_mismatch(
        self, tmp_path: Path
    ) -> None:
        """防止诊断产物写入失败覆盖真正的同名剧安全错误。"""
        page = FakePage()
        page.screenshot_error = OSError("磁盘不可写")
        configure_drama_candidates(
            page,
            [["剧A", "2026-08-10 14:36", "/detail/wrong"]],
        )

        with pytest.raises(DramaMismatchError) as caught:
            make_adapter(
                page,
                dry_run=False,
                artifact_dir=tmp_path,
            ).extract_iaa_link("剧A", TARGET_TIME, 40, 1)

        assert caught.value.code == "DRAMA_MISMATCH"
        assert caught.value.details["stage"] == "LIST"
        assert len(page.screenshot_calls) == 1

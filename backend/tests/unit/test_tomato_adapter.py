"""番茄真实 Adapter（Playwright 版）单元测试：FakePage 记录调用，不访问真实站点."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.platforms.tomato.tomato_adapter import TomatoAdapter as PlaywrightTomatoAdapter


SELECTORS = {
    "login_url": "https://tomato.example/login",
    "search_input": "#search-input",
    "search_button": "#search-button",
    "result_row": ".result-row",
    "detail_link": ".detail-link",
    "generate_button": "#generate-button",
    "episode_option": ".episode-option",
    "confirm_button": "#confirm-button",
    "link_input": "#link-input",
    "template_item": ".template-item",
    "tier_price": ".tier-price",
    "page_order": ".page-order",
}


@dataclass
class FakeLocator:
    """记录单个 locator 上发生的调用."""

    page: "FakePage"
    selector: str
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    value: str = ""
    evaluate_all_rows: list[list[str]] = field(default_factory=list)

    def fill(self, value: str, **kwargs: Any) -> None:
        self.calls.append(("fill", (value,), kwargs))

    def click(self, **kwargs: Any) -> None:
        self.calls.append(("click", (), kwargs))

    def wait_for(self, **kwargs: Any) -> None:
        self.calls.append(("wait_for", (), kwargs))

    def input_value(self, **kwargs: Any) -> str:
        self.calls.append(("input_value", (), kwargs))
        return self.value

    def evaluate_all(self, expression: str, arg: Any = None, **kwargs: Any) -> list[Any]:
        self.calls.append(("evaluate_all", (expression,), {"arg": arg, **kwargs}))
        return list(self.evaluate_all_rows)


class FakePage:
    """Playwright Page 最小 fake：按 selector 返回 FakeLocator，记录全部调用."""

    def __init__(self) -> None:
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.text_locators: dict[str, FakeLocator] = {}
        self.clipboard_text = ""
        self.evaluate_result: Any = None

    def goto(self, url: str, **kwargs: Any) -> None:
        self.calls.append(("goto", (url,), kwargs))

    def locator(self, selector: str, **kwargs: Any) -> FakeLocator:
        self.calls.append(("locator", (selector,), kwargs))
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        return self.locators[selector]

    def get_by_text(self, text: str, **kwargs: Any) -> FakeLocator:
        self.calls.append(("get_by_text", (text,), kwargs))
        if text not in self.text_locators:
            self.text_locators[text] = FakeLocator(page=self, selector=text)
        return self.text_locators[text]

    def evaluate(self, expression: str, **kwargs: Any) -> Any:
        self.calls.append(("evaluate", (expression,), kwargs))
        return self.evaluate_result

    def set_value(self, selector: str, value: str) -> None:
        """预置 locator 输入值，不产生调用记录."""
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        self.locators[selector].value = value


def make_adapter(page: FakePage | None = None, dry_run: bool = True):
    return PlaywrightTomatoAdapter(
        selectors=dict(SELECTORS),
        page=page or FakePage(),
        dry_run=dry_run,
    )


class TestFreeEntrySearch:
    """免费入口搜索流程顺序与参数验证."""

    def test_extract_iaa_link_search_flow(self):
        page = FakePage()
        page.set_value(SELECTORS["link_input"], "https://tomato.example/iaa/ep-3")
        adapter = make_adapter(page=page, dry_run=False)

        link = adapter.extract_iaa_link("剧A", 60, 3)

        assert isinstance(link, PromotionLink)
        assert link.promotion_url == "https://tomato.example/iaa/ep-3"
        assert link.source_platform == "TOMATO"
        assert link.source_entry == "FREE"
        assert link.acquisition_method == "PAGE_EXTRACTION"
        assert link.link_type == "IAA"
        assert page.calls == [
            ("goto", (SELECTORS["login_url"],), {}),
            ("locator", (SELECTORS["search_input"],), {}),
            ("locator", (SELECTORS["search_button"],), {}),
            ("locator", (SELECTORS["result_row"],), {}),
            ("locator", (SELECTORS["detail_link"],), {}),
            ("locator", (SELECTORS["generate_button"],), {}),
            ("locator", (f"{SELECTORS['episode_option']}:has-text('第3集')",), {}),
            ("locator", (SELECTORS["confirm_button"],), {}),
            ("locator", (SELECTORS["link_input"],), {}),
        ]
        assert page.locators[SELECTORS["search_input"]].calls == [
            ("fill", ("剧A",), {})
        ]
        assert page.locators[SELECTORS["search_button"]].calls == [("click", (), {})]
        assert page.locators[SELECTORS["result_row"]].calls == [("wait_for", (), {})]
        assert page.locators[SELECTORS["detail_link"]].calls == [("click", (), {})]
        assert page.locators[SELECTORS["generate_button"]].calls == [("click", (), {})]
        episode_selector = f"{SELECTORS['episode_option']}:has-text('第3集')"
        assert page.locators[episode_selector].calls == [("click", (), {})]
        assert page.locators[SELECTORS["confirm_button"]].calls == [("click", (), {})]
        assert page.locators[SELECTORS["link_input"]].calls == [("input_value", (), {})]

    def test_read_link_falls_back_to_clipboard_when_input_empty(self):
        page = FakePage()
        page.clipboard_text = "https://tomato.example/iaa/clipboard"
        page.evaluate_result = page.clipboard_text
        page.set_value(SELECTORS["link_input"], "")
        adapter = make_adapter(page=page, dry_run=False)

        link = adapter.extract_iaa_link("剧A", 40, 1)

        assert link.promotion_url == "https://tomato.example/iaa/clipboard"
        assert page.locators[SELECTORS["link_input"]].calls == [
            ("input_value", (), {})
        ]
        assert any(
            name == "evaluate" and "readText" in expression[0]
            for name, expression, _ in page.calls
        )


class TestPaidEntry:
    """付费入口模板扫描与链接生成验证."""

    def test_scan_iap_templates_returns_price_and_page_order(self):
        page = FakePage()
        page.locator(SELECTORS["template_item"]).evaluate_all_rows = [
            ["2.9", "1"],
            ["9.9", "2"],
        ]
        adapter = make_adapter(page=page, dry_run=False)

        templates = adapter.scan_iap_templates("剧A")

        assert templates == [
            TemplateInfo(
                template_id="",
                drama_name="剧A",
                title="",
                price=2.9,
                page_order=1,
            ),
            TemplateInfo(
                template_id="",
                drama_name="剧A",
                title="",
                price=9.9,
                page_order=2,
            ),
        ]
        item_locator = page.locators[SELECTORS["template_item"]]
        assert item_locator.calls[0][0] == "evaluate_all"
        expression = item_locator.calls[0][1][0]
        assert "querySelector" in expression
        arg = item_locator.calls[0][2]["arg"]
        assert arg["tier_price"] == SELECTORS["tier_price"]
        assert arg["page_order"] == SELECTORS["page_order"]

    def test_generate_iap_link_clicks_template_and_reads_link(self):
        page = FakePage()
        page.locator(SELECTORS["link_input"]).value = "https://tomato.example/iap/9-9"
        adapter = make_adapter(page=page, dry_run=False)
        template = TemplateInfo(
            template_id="tpl-9-9",
            drama_name="剧A",
            title="9.9 档模板",
            price=9.9,
            page_order=2,
        )

        link = adapter.generate_iap_link("剧A", template)

        assert isinstance(link, PromotionLink)
        assert link.promotion_url == "https://tomato.example/iap/9-9"
        assert link.source_platform == "TOMATO"
        assert link.source_entry == "PAID"
        assert link.acquisition_method == "PAGE_EXTRACTION"
        assert link.link_type == "IAP"
        assert page.text_locators["9.9 档模板"].calls == [("click", (), {})]
        assert page.locators[SELECTORS["generate_button"]].calls == [("click", (), {})]
        assert page.locators[SELECTORS["link_input"]].calls == [("input_value", (), {})]


class TestDryRun:
    """dry_run=True 只记录调用，不操作 page."""

    def test_dry_run_never_touches_page(self):
        page = FakePage()
        adapter = make_adapter(page=page, dry_run=True)

        adapter.extract_iaa_link("剧A", 60, 3)
        adapter.scan_iap_templates("剧A")
        adapter.generate_iap_link(
            "剧A",
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
            "detail_link",
            "generate_button",
            "episode_option",
            "confirm_button",
            "link_input",
            "template_item",
            "tier_price",
            "page_order",
        }
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert required_keys <= data.keys()

    def test_adapter_loads_default_selectors_from_repo_config(self):
        adapter = PlaywrightTomatoAdapter(page=None, dry_run=True)
        assert adapter._selectors["login_url"]
        assert adapter._selectors["template_item"]

    def test_adapter_satisfies_protocol(self):
        assert isinstance(make_adapter(), TomatoAdapter)

"""巨量产品库真实 Adapter（Playwright 版）单元测试：FakePage 记录调用，不访问真实站点."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from backend.domain.errors.domain_error import ExternalAdapterError
from backend.domain.ports.adapters import OceanEngineAdapter
from backend.platforms.ocean_engine.ocean_engine_adapter import (
    OceanEngineAdapter as PlaywrightOceanEngineAdapter,
)


SELECTORS = {
    "base_url": "https://ocean.example.com",
    "product_menu": ["杨硕总体户", "B组李伟层级", "资产", "商品管理", "通用版", "lw全域ROI3产品库"],
    "product_create_button": "#product-create-button",
    "product_carrier": "#product-carrier",
    "product_album_id": "#product-album-id",
    "product_copyright": "#product-copyright",
    "product_monetization": "#product-monetization",
    "product_save_button": "#product-save-button",
    "product_row": "#product-row",
    "product_id_field": "#product-id-field",
    "confirm_dialog": "#confirm-dialog",
}


@dataclass
class FakeLocator:
    """记录单个 locator 上发生的调用."""

    page: "FakePage"
    selector: str
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    value: str = ""
    element_count: int = 0

    def fill(self, value: str, **kwargs: Any) -> None:
        self.calls.append(("fill", (value,), kwargs))

    def click(self, **kwargs: Any) -> None:
        self.calls.append(("click", (), kwargs))

    def input_value(self, **kwargs: Any) -> str:
        self.calls.append(("input_value", (), kwargs))
        return self.value

    def count(self, **kwargs: Any) -> int:
        self.calls.append(("count", (), kwargs))
        return self.element_count


class FakePage:
    """Playwright Page 最小 fake：按 selector 返回 FakeLocator，记录全部调用."""

    def __init__(self) -> None:
        self.locators: dict[str, FakeLocator] = {}
        self.text_locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple[str, tuple, dict]] = []

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

    def set_value(self, selector: str, value: str) -> None:
        """预置 locator 输入值，不产生调用记录."""
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        self.locators[selector].value = value

    def set_count(self, selector: str, count: int) -> None:
        """预置 locator 元素数量，不产生调用记录."""
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        self.locators[selector].element_count = count


def make_adapter(page: FakePage | None = None, dry_run: bool = True):
    return PlaywrightOceanEngineAdapter(
        selectors=dict(SELECTORS),
        page=page or FakePage(),
        dry_run=dry_run,
    )


def _menu_click_calls() -> list[tuple[str, tuple, dict]]:
    return [
        ("get_by_text", (label,), {}) for label in SELECTORS["product_menu"]
    ]


class TestCreateProduct:
    """创建产品流程与字段填写验证."""

    def test_create_product_fills_fields_and_returns_product_id(self):
        page = FakePage()
        page.set_value(SELECTORS["product_id_field"], "prod-1")
        adapter = make_adapter(page=page, dry_run=False)

        product_id = adapter.create_product(
            "album-1",
            {
                "carrier": "端原生",
                "copyright": "厦门骑驰网络科技有限公司",
                "monetization": "付费变现+流量变现",
            },
        )

        assert product_id == "prod-1"
        assert page.calls == [
            ("goto", (SELECTORS["base_url"],), {}),
            *_menu_click_calls(),
            ("locator", (SELECTORS["product_create_button"],), {}),
            ("locator", (SELECTORS["product_carrier"],), {}),
            ("locator", (SELECTORS["product_album_id"],), {}),
            ("locator", (SELECTORS["product_copyright"],), {}),
            ("locator", (SELECTORS["product_monetization"],), {}),
            ("locator", (SELECTORS["product_save_button"],), {}),
            ("locator", (SELECTORS["confirm_dialog"],), {}),
            ("locator", (SELECTORS["product_id_field"],), {}),
        ]
        assert page.locators[SELECTORS["product_create_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["product_carrier"]].calls == [
            ("fill", ("端原生",), {})
        ]
        assert page.locators[SELECTORS["product_album_id"]].calls == [
            ("fill", ("album-1",), {})
        ]
        assert page.locators[SELECTORS["product_copyright"]].calls == [
            ("fill", ("厦门骑驰网络科技有限公司",), {})
        ]
        assert page.locators[SELECTORS["product_monetization"]].calls == [
            ("fill", ("付费变现+流量变现",), {})
        ]
        assert page.locators[SELECTORS["product_save_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["confirm_dialog"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["product_id_field"]].calls == [
            ("input_value", (), {})
        ]

    def test_create_product_uses_defaults_when_fields_empty(self):
        page = FakePage()
        page.set_value(SELECTORS["product_id_field"], "prod-2")
        adapter = make_adapter(page=page, dry_run=False)

        adapter.create_product("album-2", {})

        assert page.locators[SELECTORS["product_carrier"]].calls == [
            ("fill", ("端原生",), {})
        ]
        assert page.locators[SELECTORS["product_copyright"]].calls == [
            ("fill", ("厦门骑驰网络科技有限公司",), {})
        ]
        assert page.locators[SELECTORS["product_monetization"]].calls == [
            ("fill", ("付费变现+流量变现",), {})
        ]

    def test_create_product_uncertain_raises_result_uncertain(self):
        page = FakePage()
        page.set_value(SELECTORS["product_id_field"], "")
        adapter = make_adapter(page=page, dry_run=False)

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.create_product("album-3", {})

        assert exc.value.code == "RESULT_UNCERTAIN"


class TestVerifyProduct:
    """按产品 ID 校验产品存在性验证."""

    def test_verify_product_exists(self):
        page = FakePage()
        row_selector = f"{SELECTORS['product_row']}:has-text('prod-1')"
        page.set_count(row_selector, 1)
        adapter = make_adapter(page=page, dry_run=False)

        assert adapter.verify_product("prod-1") is True

        assert page.calls == [
            ("goto", (SELECTORS["base_url"],), {}),
            *_menu_click_calls(),
            ("locator", (row_selector,), {}),
        ]
        assert page.locators[row_selector].calls == [("count", (), {})]

    def test_verify_product_missing(self):
        page = FakePage()
        row_selector = f"{SELECTORS['product_row']}:has-text('prod-2')"
        page.set_count(row_selector, 0)
        adapter = make_adapter(page=page, dry_run=False)

        assert adapter.verify_product("prod-2") is False


class TestDryRun:
    """dry_run=True 只记录调用，不操作 page."""

    def test_dry_run_never_touches_page(self):
        page = FakePage()
        adapter = make_adapter(page=page, dry_run=True)

        product_id = adapter.create_product("album-1", {"carrier": "端原生"})
        verified = adapter.verify_product(product_id)

        assert product_id == "prod-album-1"
        assert verified is True
        assert page.calls == []
        assert [call[0] for call in adapter.recorded_calls] == [
            "create_product",
            "verify_product",
        ]

    def test_non_dry_run_does_not_record_calls(self):
        page = FakePage()
        page.set_value(SELECTORS["product_id_field"], "prod-1")
        row_selector = f"{SELECTORS['product_row']}:has-text('prod-1')"
        page.set_count(row_selector, 1)
        adapter = make_adapter(page=page, dry_run=False)

        adapter.create_product("album-1", {})
        adapter.verify_product("prod-1")

        assert adapter.recorded_calls == []


class TestConfig:
    """选择器配置与协议验证."""

    def test_default_selectors_json_has_all_required_keys(self):
        config_path = (
            Path(__file__).resolve().parents[3]
            / "configs"
            / "defaults"
            / "ocean_engine_selectors.json"
        )
        required_keys = set(SELECTORS)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert required_keys <= data.keys()
        assert data["product_menu"] == SELECTORS["product_menu"]

    def test_adapter_loads_default_selectors_from_repo_config(self):
        adapter = PlaywrightOceanEngineAdapter(page=None, dry_run=True)
        assert adapter._selectors["base_url"]
        assert adapter._selectors["product_menu"]
        assert adapter._selectors["product_id_field"]

    def test_adapter_satisfies_protocol(self):
        assert isinstance(make_adapter(), OceanEngineAdapter)

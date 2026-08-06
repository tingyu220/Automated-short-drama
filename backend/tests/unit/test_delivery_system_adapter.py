"""投放系统真实 Adapter（Playwright 版）单元测试：FakePage 记录调用，不访问真实站点."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from backend.domain.errors.domain_error import (
    ConfigurationError,
    ExternalAdapterError,
)
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import DeliverySystemAdapter, DramaAsset
from backend.platforms.delivery_system.delivery_system_adapter import (
    DeliverySystemAdapter as PlaywrightDeliverySystemAdapter,
)


SELECTORS = {
    "base_url": "https://delivery.example.com",
    "asset_search_input": "#asset-search-input",
    "asset_search_button": "#asset-search-button",
    "asset_create_button": "#asset-create-button",
    "asset_link_input": "#asset-link-input",
    "asset_save_button": "#asset-save-button",
    "album_id_field": "#album-id-field",
    "delivery_drama_id_field": "#delivery-drama-id-field",
    "config_search_input": "#config-search-input",
    "config_row": "#config-row",
    "config_create_button": "#config-create-button",
    "config_name_input": "#config-name-input",
    "config_main_drama": "#config-main-drama",
    "config_distributor": "#config-distributor",
    "config_link_input": "#config-link-input",
    "config_save_button": "#config-save-button",
    "plan_submit_button": "#plan-submit-button",
    "confirm_submit_button": "#confirm-submit-button",
    "plan_task_name": "#plan-task-name",
    "plan_account_cid": "#plan-account-cid",
    "plan_product": "#plan-product",
    "plan_promotion_config": "#plan-promotion-config",
    "task_row": "#task-row",
    "task_status_cell": "#task-status-cell",
}


@dataclass
class FakeLocator:
    """记录单个 locator 上发生的调用."""

    page: "FakePage"
    selector: str
    calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    value: str = ""
    element_count: int = 0
    text: str = ""
    rows: list[str] = field(default_factory=list)

    def fill(self, value: str, **kwargs: Any) -> None:
        self.calls.append(("fill", (value,), kwargs))

    def click(self, **kwargs: Any) -> None:
        self.calls.append(("click", (), kwargs))

    def wait_for(self, **kwargs: Any) -> None:
        self.calls.append(("wait_for", (), kwargs))

    def input_value(self, **kwargs: Any) -> str:
        self.calls.append(("input_value", (), kwargs))
        return self.value

    def count(self, **kwargs: Any) -> int:
        self.calls.append(("count", (), kwargs))
        return self.element_count

    def text_content(self, **kwargs: Any) -> str:
        self.calls.append(("text_content", (), kwargs))
        return self.text

    def evaluate_all(self, expression: str, arg: Any = None, **kwargs: Any) -> list[Any]:
        self.calls.append(("evaluate_all", (expression,), {"arg": arg, **kwargs}))
        return list(self.rows)

    def press(self, key: str, **kwargs: Any) -> None:
        self.calls.append(("press", (key,), kwargs))


class FakePage:
    """Playwright Page 最小 fake：按 selector 返回 FakeLocator，记录全部调用."""

    def __init__(self) -> None:
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple[str, tuple, dict]] = []

    def goto(self, url: str, **kwargs: Any) -> None:
        self.calls.append(("goto", (url,), kwargs))

    def locator(self, selector: str, **kwargs: Any) -> FakeLocator:
        self.calls.append(("locator", (selector,), kwargs))
        if selector not in self.locators:
            self.locators[selector] = FakeLocator(page=self, selector=selector)
        return self.locators[selector]

    def set_value(self, selector: str, value: str) -> None:
        """预置 locator 输入值，不产生调用记录."""
        self.locators.setdefault(
            selector, FakeLocator(page=self, selector=selector)
        ).value = value

    def set_count(self, selector: str, count: int) -> None:
        """预置 locator 元素数量，不产生调用记录."""
        self.locators.setdefault(
            selector, FakeLocator(page=self, selector=selector)
        ).element_count = count

    def set_text(self, selector: str, text: str) -> None:
        """预置 locator 文本，不产生调用记录."""
        self.locators.setdefault(
            selector, FakeLocator(page=self, selector=selector)
        ).text = text

    def set_rows(self, selector: str, rows: list[str]) -> None:
        """预置 evaluate_all 返回行，不产生调用记录."""
        self.locators.setdefault(
            selector, FakeLocator(page=self, selector=selector)
        ).rows = rows


def make_adapter(page: FakePage | None = None, dry_run: bool = True):
    return PlaywrightDeliverySystemAdapter(
        selectors=dict(SELECTORS),
        page=page or FakePage(),
        dry_run=dry_run,
    )


class TestDramaAsset:
    """剧目资源搜索/创建/复用验证."""

    def test_find_or_create_reuses_existing_asset(self):
        page = FakePage()
        page.set_count(SELECTORS["delivery_drama_id_field"], 1)
        page.set_value(SELECTORS["delivery_drama_id_field"], "dd-1")
        page.set_count(SELECTORS["album_id_field"], 1)
        page.set_value(SELECTORS["album_id_field"], "album-1")
        adapter = make_adapter(page=page, dry_run=False)

        asset = adapter.find_or_create_drama_asset(
            "剧A", "https://delivery.example.com/iaa/1"
        )

        assert asset == DramaAsset(
            delivery_drama_id="dd-1",
            drama_name="剧A",
            link="https://delivery.example.com/iaa/1",
            album_id="album-1",
        )
        assert SELECTORS["asset_create_button"] not in page.locators
        assert page.locators[SELECTORS["asset_search_input"]].calls == [
            ("fill", ("剧A",), {})
        ]
        assert page.locators[SELECTORS["asset_search_button"]].calls == [
            ("click", (), {})
        ]

    def test_find_or_create_creates_missing_asset(self):
        page = FakePage()
        page.set_value(SELECTORS["delivery_drama_id_field"], "dd-2")
        page.set_value(SELECTORS["album_id_field"], "album-2")
        adapter = make_adapter(page=page, dry_run=False)

        asset = adapter.find_or_create_drama_asset(
            "剧B", "https://delivery.example.com/iaa/2"
        )

        assert asset == DramaAsset(
            delivery_drama_id="dd-2",
            drama_name="剧B",
            link="https://delivery.example.com/iaa/2",
            album_id="album-2",
        )
        assert page.locators[SELECTORS["asset_create_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["asset_link_input"]].calls == [
            ("fill", ("https://delivery.example.com/iaa/2",), {})
        ]
        assert page.locators[SELECTORS["asset_save_button"]].calls == [
            ("click", (), {})
        ]

    def test_create_uncertain_raises_result_uncertain(self):
        page = FakePage()
        page.set_value(SELECTORS["delivery_drama_id_field"], "")
        page.set_value(SELECTORS["album_id_field"], "")
        adapter = make_adapter(page=page, dry_run=False)

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.find_or_create_drama_asset("剧C", "https://delivery.example.com/iaa/3")

        assert exc.value.code == "RESULT_UNCERTAIN"


class TestPromotionConfig:
    """推广内容配置缺失项创建与主剧校验验证."""

    def test_create_missing_fills_fields_and_returns_result(self):
        page = FakePage()
        page.set_rows(SELECTORS["task_row"], [])
        page.set_text(SELECTORS["task_status_cell"], "OK")
        adapter = make_adapter(page=page, dry_run=False)

        result = adapter.ensure_promotion_config(
            "dd-1",
            "IAA",
            "https://delivery.example.com/iaa/1",
            "剧A",
            "TOMATO",
        )

        assert result == "OK"
        assert page.locators[SELECTORS["config_search_input"]].calls == [
            ("fill", ("IAA-TOMATO-剧A",), {}),
            ("press", ("Enter",), {}),
        ]
        assert page.locators[SELECTORS["config_row"]].calls == [
            ("evaluate_all", ("(rows) => rows.map(row => row.innerText.trim())",), {"arg": None})
        ]
        assert page.locators[SELECTORS["config_create_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["config_name_input"]].calls == [
            ("fill", ("IAA-TOMATO-剧A",), {})
        ]
        assert page.locators[SELECTORS["config_main_drama"]].calls == [
            ("fill", ("剧A",), {})
        ]
        assert page.locators[SELECTORS["config_distributor"]].calls == [
            ("fill", ("微智造",), {})
        ]
        assert page.locators[SELECTORS["config_link_input"]].calls == [
            ("fill", ("https://delivery.example.com/iaa/1",), {})
        ]
        assert page.locators[SELECTORS["config_save_button"]].calls == [
            ("click", (), {})
        ]

    def test_create_missing_reuses_existing_config(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], ["IAA-TOMATO-剧A"])
        adapter = make_adapter(page=page, dry_run=False)

        result = adapter.ensure_promotion_config(
            "dd-1", "IAA", "link", "剧A", "TOMATO"
        )

        assert result == "IAA-TOMATO-剧A"
        assert SELECTORS["config_create_button"] not in page.locators

    def test_create_missing_raises_drama_mismatch(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], [])
        page.set_text(SELECTORS["task_status_cell"], "DRAMA_MISMATCH: 链接与主剧不一致")
        adapter = make_adapter(page=page, dry_run=False)

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.ensure_promotion_config(
                "dd-1", "IAA", "link", "剧A", "TOMATO"
            )

        assert exc.value.code == "PROMOTION_LINK_DRAMA_MISMATCH"

    def test_create_missing_empty_result_raises_result_uncertain(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], [])
        page.set_text(SELECTORS["task_status_cell"], "")
        adapter = make_adapter(page=page, dry_run=False)

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.ensure_promotion_config(
                "dd-1", "IAA", "link", "剧A", "TOMATO"
            )

        assert exc.value.code == "RESULT_UNCERTAIN"


class TestPlanSubmit:
    """标准投放计划提交验证."""

    def test_submit_returns_external_task_id(self):
        page = FakePage()
        page.set_text(SELECTORS["task_row"], "task-20260806-001")
        adapter = make_adapter(page=page, dry_run=False)
        spec = PlanSpec(
            drama_name="剧A",
            platform="TOMATO",
            task_name="番茄#端免剧A测试任务",
            link_set={"IAA": "https://delivery.example.com/iaa/1"},
            account_cids=["cid-1", "cid-2"],
            product_id="prod-1",
        )

        task_id = adapter.submit_plan(spec)

        assert task_id == "task-20260806-001"
        assert page.locators[SELECTORS["plan_task_name"]].calls == [
            ("fill", ("番茄#端免剧A测试任务",), {})
        ]
        assert page.locators[SELECTORS["plan_account_cid"]].calls == [
            ("fill", ("cid-1",), {})
        ]
        assert page.locators[SELECTORS["plan_product"]].calls == [
            ("fill", ("prod-1",), {})
        ]
        assert page.locators[SELECTORS["plan_promotion_config"]].calls == [
            ("fill", ("https://delivery.example.com/iaa/1",), {})
        ]
        assert page.locators[SELECTORS["plan_submit_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["confirm_submit_button"]].calls == [
            ("click", (), {})
        ]

    def test_submit_uncertain_raises_result_uncertain(self):
        page = FakePage()
        page.set_text(SELECTORS["task_row"], "")
        adapter = make_adapter(page=page, dry_run=False)
        spec = PlanSpec(
            drama_name="剧A",
            platform="TOMATO",
            task_name="番茄#端免剧A测试任务",
            link_set={"IAA": "link"},
            account_cids=["cid-1"],
            product_id="prod-1",
        )

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.submit_plan(spec)

        assert exc.value.code == "RESULT_UNCERTAIN"

    def test_submit_missing_selector_raises_configuration_error(self):
        selectors = dict(SELECTORS)
        del selectors["plan_product"]
        adapter = PlaywrightDeliverySystemAdapter(
            selectors=selectors, page=FakePage(), dry_run=False
        )
        spec = PlanSpec(
            drama_name="剧A",
            platform="TOMATO",
            task_name="番茄#端免剧A测试任务",
            link_set={"IAA": "link"},
            account_cids=["cid-1"],
            product_id="prod-1",
        )

        with pytest.raises(ConfigurationError) as exc:
            adapter.submit_plan(spec)

        assert exc.value.code == "CONFIGURATION_ERROR"


class TestTaskStatus:
    """任务状态轮询读取与归一化验证."""

    def _status_selector(self, external_task_id: str) -> str:
        return (
            f"{SELECTORS['task_row']}:has-text('{external_task_id}') "
            f"{SELECTORS['task_status_cell']}"
        )

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("已完成", "COMPLETED"),
            ("COMPLETED", "COMPLETED"),
            ("部分失败", "PARTIAL_FAILED"),
            ("FAILED", "FAILED"),
            ("投放中", "OTHER"),
        ],
    )
    def test_poll_maps_status(self, raw, expected):
        page = FakePage()
        page.set_text(self._status_selector("task-1"), raw)
        adapter = make_adapter(page=page, dry_run=False)

        assert adapter.poll_task_status("task-1") == expected

    def test_poll_missing_row_raises_result_uncertain(self):
        page = FakePage()
        page.set_text(self._status_selector("task-1"), "")
        adapter = make_adapter(page=page, dry_run=False)

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.poll_task_status("task-1")

        assert exc.value.code == "RESULT_UNCERTAIN"


class TestDryRun:
    """dry_run=True 只记录调用，不操作 page."""

    def test_dry_run_never_touches_page(self):
        page = FakePage()
        adapter = make_adapter(page=page, dry_run=True)

        adapter.find_or_create_drama_asset("剧A", "link")
        adapter.ensure_promotion_config("dd-1", "IAA", "link", "剧A", "TOMATO")
        adapter.submit_plan({"drama_name": "剧A"})
        adapter.poll_task_status("task-1")

        assert page.calls == []
        assert [call[0] for call in adapter.recorded_calls] == [
            "find_or_create_drama_asset",
            "ensure_promotion_config",
            "submit_plan",
            "poll_task_status",
        ]

    def test_non_dry_run_does_not_record_calls(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], [])
        page.set_text(SELECTORS["task_status_cell"], "OK")
        page.set_text(SELECTORS["task_row"], "task-1")
        page.set_text(
            f"{SELECTORS['task_row']}:has-text('task-1') "
            f"{SELECTORS['task_status_cell']}",
            "COMPLETED",
        )
        page.set_value(SELECTORS["delivery_drama_id_field"], "dd-1")
        page.set_value(SELECTORS["album_id_field"], "album-1")
        adapter = make_adapter(page=page, dry_run=False)

        adapter.find_or_create_drama_asset("剧A", "link")
        adapter.ensure_promotion_config("dd-1", "IAA", "link", "剧A", "TOMATO")
        adapter.submit_plan(
            PlanSpec(
                drama_name="剧A",
                platform="TOMATO",
                task_name="task-name",
                link_set={"IAA": "link"},
                account_cids=["cid-1"],
                product_id="prod-1",
            )
        )
        adapter.poll_task_status("task-1")

        assert adapter.recorded_calls == []


class TestConfig:
    """选择器配置与协议验证."""

    def test_default_selectors_json_has_all_required_keys(self):
        config_path = (
            Path(__file__).resolve().parents[3]
            / "configs"
            / "defaults"
            / "delivery_system_selectors.json"
        )
        required_keys = set(SELECTORS)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert required_keys <= data.keys()

    def test_adapter_loads_default_selectors_from_repo_config(self):
        adapter = PlaywrightDeliverySystemAdapter(page=None, dry_run=True)
        assert adapter._selectors["base_url"]
        assert adapter._selectors["task_status_cell"]

    def test_adapter_satisfies_protocol(self):
        assert isinstance(make_adapter(), DeliverySystemAdapter)

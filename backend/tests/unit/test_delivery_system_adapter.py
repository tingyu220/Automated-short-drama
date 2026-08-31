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
from backend.domain.plans.delivery_form_spec import CidFormRow, DeliveryFormSpec
from backend.domain.ports.adapters import DeliverySystemAdapter, DramaAsset
from backend.platforms.delivery_system.delivery_system_adapter import (
    DeliverySystemAdapter as PlaywrightDeliverySystemAdapter,
)


SELECTORS = {
    "base_url": "https://delivery.example.com",
    "asset_page_url": "https://delivery.example.com/video/dramas",
    "config_page_url": "https://delivery.example.com/autoTask/proContentConfig/index",
    "asset_search_input": "#asset-search-input",
    "asset_search_button": "#asset-search-button",
    "asset_create_button": "#asset-create-button",
    "asset_drama_name_input": "#asset-drama-name-input",
    "asset_link_input": "#asset-link-input",
    "asset_save_button": "#asset-save-button",
    "album_id_field": "#album-id-field",
    "delivery_drama_id_field": "#delivery-drama-id-field",
    "config_search_input": "#config-search-input",
    "config_row": "#config-row",
    "config_create_button": "#config-create-button",
    "config_name_input": "#config-name-input",
    "config_main_drama": "#config-main-drama",
    "config_ad_type": "#config-ad-type",
    "config_distributor": "#config-distributor",
    "config_link_input": "#config-link-input",
    "config_save_button": "#config-save-button",
    "plan_submit_button": "#plan-submit-button",
    "confirm_submit_button": "#confirm-submit-button",
    "plan_task_name": "#plan-task-name",
    "plan_type": "#plan-type",
    "plan_account_cid": "#plan-account-cid-{index}",
    "plan_douyin_account": "#plan-douyin-account-{index}",
    "plan_account_open_preset": "#plan-open-preset-{index}",
    "plan_ad_preset": "#plan-ad-preset-{index}",
    "plan_promotion_config": "#plan-promotion-config-{index}",
    "plan_material": "#plan-material-{index}",
    "plan_title_package": "#plan-title-package-{index}",
    "plan_title_shuffle_button": "#plan-title-shuffle",
    "plan_project_rule": "#plan-project-rule",
    "plan_ad_rule": "#plan-ad-rule",
    "plan_material_average": "#plan-material-average",
    "plan_title_average": "#plan-title-average",
    "plan_material_group_count": "#plan-material-group-count",
    "plan_ad_limit": "#plan-ad-limit",
    "plan_project_count": "#plan-project-count",
    "task_row": "#task-row",
    "task_status_cell": "#task-status-cell",
    "task_id_cell": "#task-id-cell",
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
    rows_sequence: list[list[str]] = field(default_factory=list)
    _evaluate_count: int = 0

    def fill(self, value: str, **kwargs: Any) -> None:
        self.calls.append(("fill", (value,), kwargs))

    def click(self, **kwargs: Any) -> None:
        kwargs.pop("timeout", None)
        self.calls.append(("click", (), kwargs))

    def wait_for(self, **kwargs: Any) -> None:
        kwargs.pop("timeout", None)
        self.calls.append(("wait_for", (), kwargs))

    def input_value(self, **kwargs: Any) -> str:
        kwargs.pop("timeout", None)
        self.calls.append(("input_value", (), kwargs))
        return self.value

    def count(self, **kwargs: Any) -> int:
        self.calls.append(("count", (), kwargs))
        return self.element_count

    def text_content(self, **kwargs: Any) -> str:
        kwargs.pop("timeout", None)
        self.calls.append(("text_content", (), kwargs))
        return self.text

    def evaluate_all(self, expression: str, arg: Any = None, **kwargs: Any) -> list[Any]:
        self.calls.append(("evaluate_all", (expression,), {"arg": arg, **kwargs}))
        if self.rows_sequence:
            idx = min(self._evaluate_count, len(self.rows_sequence) - 1)
            self._evaluate_count += 1
            return list(self.rows_sequence[idx])
        return list(self.rows)

    def press(self, key: str, **kwargs: Any) -> None:
        self.calls.append(("press", (key,), kwargs))

    @property
    def first(self) -> "FakeLocator":
        return self

    def filter(self, **kwargs: Any) -> "FakeLocator":
        return self

    def locator(self, selector: str) -> "FakeLocator":
        return self.page.locator(selector)

    def evaluate(self, expression: str, arg: Any = None, **kwargs: Any) -> Any:
        self.calls.append(("evaluate", (expression,), {"arg": arg, **kwargs}))
        return None

    def is_visible(self, **kwargs: Any) -> bool:
        self.calls.append(("is_visible", (), kwargs))
        return False

    def inner_text(self, **kwargs: Any) -> str:
        self.calls.append(("inner_text", (), kwargs))
        return self.text


class FakePage:
    """Playwright Page 最小 fake：按 selector 返回 FakeLocator，记录全部调用."""

    def __init__(self) -> None:
        self.locators: dict[str, FakeLocator] = {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.url: str = "https://delivery.example.com/page"

    def goto(self, url: str, **kwargs: Any) -> None:
        kwargs.pop("wait_until", None)
        kwargs.pop("timeout", None)
        self.calls.append(("goto", (url,), kwargs))

    def wait_for_timeout(self, ms: int, **kwargs: Any) -> None:
        self.calls.append(("wait_for_timeout", (ms,), kwargs))

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

    def set_rows_sequence(self, selector: str, rows_list: list[list[str]]) -> None:
        """预置 evaluate_all 连续调用返回不同行列表."""
        loc = self.locators.setdefault(
            selector, FakeLocator(page=self, selector=selector)
        )
        loc.rows_sequence = rows_list


def make_adapter(page: FakePage | None = None, dry_run: bool = True):
    return PlaywrightDeliverySystemAdapter(
        selectors=dict(SELECTORS),
        page=page or FakePage(),
        dry_run=dry_run,
    )


def make_form() -> DeliveryFormSpec:
    return DeliveryFormSpec(
        drama_name="剧A",
        task_name="番茄#端免剧A测试任务",
        plan_type="端免",
        cid_rows=(
            CidFormRow("cid-1", "dy-1", "open-1", "ad-1", "iaa-番茄-剧A", "IAA"),
            CidFormRow("cid-2", "dy-2", "open-2", "ad-2", "iaa-番茄-剧A", "IAA"),
        ),
        material_ids=("material-1", "material-2", "material-3"),
        title_packages=tuple(f"title-{index}" for index in range(6)),
        material_group_count=3,
        ad_limit_per_project=1,
        project_count=3,
    )


class TestDramaAsset:
    """剧目资源搜索/创建/复用验证."""

    def test_find_or_create_reuses_existing_asset(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], ["剧A\t番茄\t账号A"])
        adapter = make_adapter(page=page, dry_run=False)

        asset = adapter.find_or_create_drama_asset(
            "剧A", "https://delivery.example.com/iaa/1"
        )

        assert asset.drama_name == "剧A"
        assert asset.link == "https://delivery.example.com/iaa/1"
        assert SELECTORS["asset_create_button"] not in page.locators
        assert page.locators[SELECTORS["asset_search_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("fill", ("剧A",), {}),
        ]
        assert page.locators[SELECTORS["asset_search_button"]].calls == [
            ("click", (), {})
        ]

    def test_find_or_create_creates_missing_asset(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], [])
        page.set_value(SELECTORS["album_id_field"], "album-2")
        adapter = make_adapter(page=page, dry_run=False)

        asset = adapter.find_or_create_drama_asset(
            "剧B", "https://delivery.example.com/iaa/2"
        )

        assert asset.delivery_drama_id == "album-2"
        assert asset.drama_name == "剧B"
        assert asset.link == "https://delivery.example.com/iaa/2"
        assert asset.album_id == "album-2"
        assert page.locators[SELECTORS["asset_create_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["asset_drama_name_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("fill", ("剧B",), {}),
        ]
        assert page.locators[SELECTORS["asset_link_input"]].calls == [
            ("fill", ("https://delivery.example.com/iaa/2",), {})
        ]
        assert page.locators[SELECTORS["asset_save_button"]].calls == [
            ("click", (), {})
        ]

    def test_create_uncertain_raises_result_uncertain(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], [])
        page.set_value(SELECTORS["album_id_field"], "")
        adapter = make_adapter(page=page, dry_run=False)

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.find_or_create_drama_asset("剧C", "https://delivery.example.com/iaa/3")

        assert exc.value.code == "RESULT_UNCERTAIN"


class TestPromotionConfig:
    """推广内容配置缺失项创建与表格验证."""

    def test_create_missing_fills_fields_and_returns_result(self):
        page = FakePage()
        page.set_rows_sequence(
            SELECTORS["config_row"],
            [
                [],
                [],
                [],
                ["iaa-番茄-剧A\t冰封末世\t番茄\t付费\t微智造\tlink\tB组\t删除复制"],
            ],
        )
        page.set_count(".el-select-dropdown__item:visible", 1)
        adapter = make_adapter(page=page, dry_run=False)

        result = adapter.ensure_promotion_config(
            "dd-1",
            "IAA",
            "https://delivery.example.com/iaa/1",
            "剧A",
            "TOMATO",
        )

        assert result == "iaa-番茄-剧A"
        assert page.locators[SELECTORS["config_search_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("fill", ("iaa-番茄-剧A",), {}),
            ("press", ("Enter",), {}),
            ("fill", ("iaa-番茄-剧A",), {}),
            ("press", ("Enter",), {}),
            ("fill", ("iaa-番茄-剧A",), {}),
            ("press", ("Enter",), {}),
            ("wait_for", (), {"state": "visible"}),
            ("fill", ("iaa-番茄-剧A",), {}),
            ("press", ("Enter",), {}),
        ]
        assert page.locators[SELECTORS["config_create_button"]].calls == [
            ("click", (), {})
        ]
        assert page.locators[SELECTORS["config_name_input"]].calls == [
            ("wait_for", (), {"state": "visible"}),
            ("fill", ("iaa-番茄-剧A",), {}),
        ]
        # _fill_select_input uses JS evaluate to click el-select, then selects option
        assert len(page.locators[SELECTORS["config_main_drama"]].calls) == 2
        assert page.locators[SELECTORS["config_main_drama"]].calls[0][0] == "evaluate"
        assert len(page.locators[SELECTORS["config_ad_type"]].calls) == 2
        assert page.locators[SELECTORS["config_ad_type"]].calls[0][0] == "evaluate"
        assert len(page.locators[SELECTORS["config_distributor"]].calls) == 2
        assert page.locators[SELECTORS["config_distributor"]].calls[0][0] == "evaluate"
        assert page.locators[".el-select-dropdown__item:visible"].calls == [
            ("count", (), {}),
            ("click", (), {}),
            ("count", (), {}),
            ("click", (), {}),
            ("count", (), {}),
            ("click", (), {}),
        ]
        assert page.locators[SELECTORS["config_link_input"]].calls == [
            ("fill", ("https://delivery.example.com/iaa/1",), {})
        ]
        assert page.locators[SELECTORS["config_save_button"]].calls == [
            ("click", (), {})
        ]

    def test_create_missing_reuses_existing_config(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], ["iaa-番茄-剧A"])
        adapter = make_adapter(page=page, dry_run=False)

        result = adapter.ensure_promotion_config(
            "dd-1", "IAA", "link", "剧A", "TOMATO"
        )

        assert result == "iaa-番茄-剧A"
        assert SELECTORS["config_create_button"] not in page.locators

    def test_create_missing_empty_result_raises_result_uncertain(self):
        page = FakePage()
        page.set_rows(SELECTORS["config_row"], [])
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
        spec = make_form()

        task_id = adapter.submit_plan(spec)

        assert task_id == "task-20260806-001"
        assert page.locators[SELECTORS["plan_task_name"]].calls == [
            ("fill", ("番茄#端免剧A测试任务",), {})
        ]
        for index, cid in enumerate(("cid-1", "cid-2")):
            selector = SELECTORS["plan_account_cid"].format(index=index)
            assert page.locators[selector].calls == [("fill", (cid,), {})]
        assert page.locators[SELECTORS["plan_material"].format(index=2)].calls == [
            ("fill", ("material-3",), {})
        ]
        assert page.locators[SELECTORS["plan_title_package"].format(index=5)].calls == [
            ("fill", ("title-5",), {})
        ]
        assert page.locators[SELECTORS["plan_title_shuffle_button"]].calls == [
            ("click", (), {})
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
        spec = make_form()

        with pytest.raises(ExternalAdapterError) as exc:
            adapter.submit_plan(spec)

        assert exc.value.code == "RESULT_UNCERTAIN"

    def test_submit_missing_selector_raises_configuration_error(self):
        selectors = dict(SELECTORS)
        del selectors["plan_title_package"]
        adapter = PlaywrightDeliverySystemAdapter(
            selectors=selectors, page=FakePage(), dry_run=False
        )
        spec = make_form()

        with pytest.raises(ConfigurationError) as exc:
            adapter.submit_plan(spec)

        assert exc.value.code == "CONFIGURATION_ERROR"


class TestTaskStatus:
    """任务状态轮询读取与归一化验证."""

    def test_find_task_by_idempotency_key_returns_task_id(self):
        page = FakePage()
        selector = (
            f"{SELECTORS['task_row']}:has-text('唯一任务名') "
            f"{SELECTORS['task_id_cell']}"
        )
        page.set_text(selector, "task-001")
        adapter = PlaywrightDeliverySystemAdapter(
            selectors=dict(SELECTORS), page=page, dry_run=False
        )

        assert adapter.find_task_by_idempotency_key("唯一任务名") == "task-001"

    def test_find_task_by_idempotency_key_returns_none_when_absent(self):
        adapter = PlaywrightDeliverySystemAdapter(
            selectors=dict(SELECTORS), page=FakePage(), dry_run=False
        )

        assert adapter.find_task_by_idempotency_key("不存在") is None

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
        page.set_rows(SELECTORS["config_row"], ["iaa-番茄-剧A"])
        page.set_text(SELECTORS["task_row"], "task-1")
        page.set_text(
            f"{SELECTORS['task_row']}:has-text('task-1') "
            f"{SELECTORS['task_status_cell']}",
            "COMPLETED",
        )
        adapter = make_adapter(page=page, dry_run=False)

        adapter.find_or_create_drama_asset("剧A", "link")
        adapter.ensure_promotion_config("dd-1", "IAA", "link", "剧A", "TOMATO")
        adapter.submit_plan(make_form())
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

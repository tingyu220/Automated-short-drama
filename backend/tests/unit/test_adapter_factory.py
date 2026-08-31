"""真实/ Mock Adapter 工厂接线测试。"""
from __future__ import annotations

import pytest

from backend.bootstrap.adapters import (
    AdapterBundle,
    build_adapters,
    build_drama_sheet_adapter,
)
from backend.domain.errors.domain_error import ConfigurationError
from backend.infrastructure.config.settings import Settings
from backend.platforms.delivery_system.delivery_system_adapter import (
    DeliverySystemAdapter as RealDeliverySystemAdapter,
)
from backend.platforms.feishu.feishu_adapter import FeishuAdapter as RealFeishuAdapter
from backend.platforms.feishu.drama_sheet_adapter import DramaSheetAdapter
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter
from backend.platforms.ocean_engine.ocean_engine_adapter import (
    OceanEngineAdapter as RealOceanEngineAdapter,
)
from backend.platforms.tomato.tomato_adapter import TomatoAdapter as RealTomatoAdapter


class FakePage:
    """Playwright page 占位对象。"""


class TestBuildAdapters:
    """Adapter 工厂按开关组装 Mock / 真实四件套。"""

    def test_default_returns_mock_bundle(self, monkeypatch) -> None:
        monkeypatch.delenv("WORKBUDDY_USE_REAL_ADAPTERS", raising=False)

        bundle = build_adapters(Settings())

        assert isinstance(bundle, AdapterBundle)
        assert isinstance(bundle.feishu, MockFeishuAdapter)
        assert isinstance(bundle.tomato, MockTomatoAdapter)
        assert isinstance(bundle.delivery, MockDeliverySystemAdapter)
        assert isinstance(bundle.ocean, MockOceanEngineAdapter)

    def test_explicit_false_returns_mock_bundle(self, monkeypatch) -> None:
        monkeypatch.setenv("WORKBUDDY_USE_REAL_ADAPTERS", "true")

        bundle = build_adapters(Settings(), use_real=False)

        assert isinstance(bundle.feishu, MockFeishuAdapter)
        assert isinstance(bundle.tomato, MockTomatoAdapter)
        assert isinstance(bundle.delivery, MockDeliverySystemAdapter)
        assert isinstance(bundle.ocean, MockOceanEngineAdapter)

    def test_env_true_without_page_raises_configuration_error(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("WORKBUDDY_USE_REAL_ADAPTERS", "true")
        monkeypatch.delenv("WORKBUDDY_FEISHU_TASK_SHEET_URL", raising=False)
        monkeypatch.delenv("WORKBUDDY_FEISHU_TASK_SHEET_NAME", raising=False)

        with pytest.raises(ConfigurationError):
            build_adapters(Settings())

    def test_env_true_with_fake_page_returns_real_bundle(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("WORKBUDDY_USE_REAL_ADAPTERS", "true")
        monkeypatch.setenv(
            "WORKBUDDY_FEISHU_TASK_SHEET_URL", "https://feishu.cn/sheets/mock"
        )
        monkeypatch.setenv("WORKBUDDY_FEISHU_TASK_SHEET_NAME", "剧目表")

        bundle = build_adapters(Settings(), page=FakePage())

        assert isinstance(bundle.feishu, RealFeishuAdapter)
        assert isinstance(bundle.tomato, RealTomatoAdapter)
        assert isinstance(bundle.delivery, RealDeliverySystemAdapter)
        assert isinstance(bundle.ocean, RealOceanEngineAdapter)

    def test_settings_true_is_the_factory_source_of_truth(self, monkeypatch) -> None:
        monkeypatch.delenv("WORKBUDDY_USE_REAL_ADAPTERS", raising=False)
        monkeypatch.setenv(
            "WORKBUDDY_FEISHU_TASK_SHEET_URL", "https://feishu.cn/sheets/mock"
        )
        monkeypatch.setenv("WORKBUDDY_FEISHU_TASK_SHEET_NAME", "剧目表")

        bundle = build_adapters(
            Settings(use_real_adapters=True),
            page=FakePage(),
        )

        assert isinstance(bundle.feishu, RealFeishuAdapter)
        assert isinstance(bundle.tomato, RealTomatoAdapter)
        assert isinstance(bundle.delivery, RealDeliverySystemAdapter)

    def test_real_bundle_uses_feishu_configuration_from_settings(
        self, monkeypatch
    ) -> None:
        """Settings 已加载 .env 时，不应再强制要求进程环境变量。"""
        monkeypatch.delenv("WORKBUDDY_FEISHU_TASK_SHEET_URL", raising=False)
        monkeypatch.delenv("WORKBUDDY_FEISHU_TASK_SHEET_NAME", raising=False)
        settings = Settings(
            use_real_adapters=True,
            feishu_task_sheet_url="https://feishu.cn/sheets/from-settings",
            feishu_task_sheet_name="剧目表",
        )

        bundle = build_adapters(settings, page=FakePage())

        assert bundle.feishu._task_sheet_url == "https://feishu.cn/sheets/from-settings"
        assert bundle.feishu._task_sheet_name == "剧目表"

    def test_real_bundle_explicitly_disables_dry_run(self, monkeypatch) -> None:
        """真实模式必须显式传 dry_run=False，默认路径保持 dry_run。"""
        monkeypatch.setenv("WORKBUDDY_USE_REAL_ADAPTERS", "true")
        monkeypatch.setenv(
            "WORKBUDDY_FEISHU_TASK_SHEET_URL", "https://feishu.cn/sheets/mock"
        )
        monkeypatch.setenv("WORKBUDDY_FEISHU_TASK_SHEET_NAME", "剧目表")

        bundle = build_adapters(Settings(), page=FakePage())

        assert bundle.feishu._dry_run is False
        assert bundle.tomato._dry_run is False
        assert bundle.delivery._dry_run is False
        assert bundle.ocean._dry_run is False

    def test_real_bundle_overrides_placeholder_base_urls_from_settings(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv(
            "WORKBUDDY_FEISHU_TASK_SHEET_URL", "https://feishu.cn/sheets/mock"
        )
        monkeypatch.setenv("WORKBUDDY_FEISHU_TASK_SHEET_NAME", "剧目表")
        settings = Settings(
            use_real_adapters=True,
            tomato_base_url="https://tomato.real.example",
            delivery_base_url="https://delivery.real.example",
            ocean_base_url="https://ocean.real.example",
        )

        bundle = build_adapters(settings, page=FakePage())

        assert bundle.tomato._selectors["login_url"] == (
            "https://tomato.real.example/sale/short-play/list"
        )
        assert bundle.delivery._selectors["base_url"] == (
            "https://delivery.real.example"
        )
        assert bundle.ocean._selectors["base_url"] == "https://ocean.real.example"


def test_build_drama_sheet_adapter_uses_source_and_private_settings():
    settings = Settings(
        feishu_source_sheet_url="https://feishu.cn/wiki/public",
        feishu_source_sheet_id="sM4NAq",
        feishu_private_sheet_url="https://feishu.cn/wiki/private",
        feishu_private_sheet_id="a8d032",
    )

    adapter = build_drama_sheet_adapter(settings)

    assert isinstance(adapter, DramaSheetAdapter)
    assert adapter._public_sheet_id == "sM4NAq"
    assert adapter._private_sheet_id == "a8d032"

"""真实/ Mock Adapter 工厂接线测试。"""
from __future__ import annotations

import pytest

from backend.bootstrap.adapters import AdapterBundle, build_adapters
from backend.domain.errors.domain_error import ConfigurationError
from backend.infrastructure.config.settings import Settings
from backend.platforms.delivery_system.delivery_system_adapter import (
    DeliverySystemAdapter as RealDeliverySystemAdapter,
)
from backend.platforms.feishu.feishu_adapter import FeishuAdapter as RealFeishuAdapter
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

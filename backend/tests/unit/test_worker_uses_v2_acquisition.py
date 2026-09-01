"""验证 Worker 真实模式使用 V2 Acquisition 而非 Legacy DOM。"""
from __future__ import annotations

import pytest

from backend.bootstrap.native_link_acquisition import (
    ConfigurationError,
    build_native_link_acquisition,
)
from backend.domain.acquisition.scoped_network_provider import ScopedNetworkProvider
from backend.application.services.link_acquisition_service import LinkAcquisitionService
from backend.platforms.mock.mock_tomato import MockTomatoAdapter
from backend.platforms.tomato.providers.legacy_dom_provider import LegacyDomProvider
from backend.platforms.tomato.providers.network_provider import NetworkProvider


class _FakePage:
    """最小化 Page 模拟，用于 NetworkListener 注册。"""

    def __init__(self):
        self._listeners: dict[str, list] = {}

    def on(self, event, handler):
        self._listeners.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        if event in self._listeners:
            self._listeners[event] = [
                h for h in self._listeners[event] if h is not handler
            ]


class _MemoryPromotionAssetRepo:
    def save_all(self, assets):
        return assets


def _price_rules():
    from backend.domain.rules.template_price_rule import TemplatePriceRule

    return [
        TemplatePriceRule(target_price=2.9, min_price=2.0, max_price=5.0, key="iap_2_9"),
        TemplatePriceRule(target_price=9.9, min_price=7.0, max_price=15.0, key="iap_9_9"),
    ]


class TestBuildNativeLinkAcquisition:
    """验证 Composition Root 组装逻辑。"""

    def test_real_mode_returns_v2_chain(self):
        """真实模式（page 可用）返回 ScopedNetworkProvider。"""
        page = _FakePage()
        tomato = MockTomatoAdapter()
        result = build_native_link_acquisition(
            tomato=tomato,
            price_rules=_price_rules(),
            page=page,
            promotion_asset_repo=_MemoryPromotionAssetRepo(),
        )
        assert isinstance(result, LinkAcquisitionService)
        provider = result._provider
        assert isinstance(provider, ScopedNetworkProvider)

    def test_real_mode_without_page_raises(self):
        """真实模式无 page → ConfigurationError。"""
        tomato = MockTomatoAdapter()
        with pytest.raises(ConfigurationError):
            build_native_link_acquisition(
                tomato=tomato,
                price_rules=_price_rules(),
                page=None,
                promotion_asset_repo=_MemoryPromotionAssetRepo(),
            )

    def test_mock_mode_returns_legacy_default(self):
        """Mock 模式（allow_legacy=True）返回 LegacyDomProvider。"""
        tomato = MockTomatoAdapter()
        result = build_native_link_acquisition(
            tomato=tomato,
            price_rules=_price_rules(),
            page=None,
            promotion_asset_repo=_MemoryPromotionAssetRepo(),
            allow_legacy=True,
        )
        assert isinstance(result, LinkAcquisitionService)
        assert isinstance(result._provider, LegacyDomProvider)

    def test_mock_mode_without_legacy_raises(self):
        """Mock 模式不允许 Legacy → ConfigurationError。"""
        tomato = MockTomatoAdapter()
        with pytest.raises(ConfigurationError):
            build_native_link_acquisition(
                tomato=tomato,
                price_rules=_price_rules(),
                page=None,
                promotion_asset_repo=_MemoryPromotionAssetRepo(),
                allow_legacy=False,
            )

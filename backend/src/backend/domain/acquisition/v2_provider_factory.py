"""V2 Provider 工厂（Phase 9）。

按优先级构建 Provider 链：
    API → Network → DOM (Legacy)

根据运行模式（ShadowMode）选择包装方式：
- LEGACY: 只用 Legacy DOM
- SHADOW: Legacy 走生产 + Network 观察
- V2: API → Network → DOM FallbackChain
"""
from __future__ import annotations

import logging
from typing import Any

from backend.domain.acquisition.fallback_chain import FallbackChainProvider
from backend.domain.acquisition.shadow_provider import (
    ShadowMode,
    ShadowModeProvider,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule

logger = logging.getLogger(__name__)


class V2ProviderFactory:
    """构建 V2 Provider 链。"""

    @staticmethod
    def build(
        *,
        legacy_provider: Any | None = None,
        network_provider: Any | None = None,
        api_client: Any | None = None,
        price_rules: list[TemplatePriceRule] | None = None,
        mode: ShadowMode = ShadowMode.V2,
    ) -> Any:
        """根据模式构建 Provider。

        V2 模式: FallbackChain([API, Network, DOM])
        SHADOW 模式: ShadowModeProvider(Legacy, Network)
        LEGACY 模式: 直接返回 Legacy
        """
        if mode == ShadowMode.LEGACY:
            if legacy_provider is None:
                raise ValueError("LEGACY mode requires legacy_provider")
            return legacy_provider

        if mode == ShadowMode.SHADOW:
            if legacy_provider is None or network_provider is None:
                raise ValueError("SHADOW mode requires legacy_provider and network_provider")
            return ShadowModeProvider(
                legacy=legacy_provider,
                network=network_provider,
                mode=ShadowMode.SHADOW,
            )

        # V2 模式
        providers: list[Any] = []

        if api_client is not None and price_rules:
            from backend.platforms.tomato.providers.api_provider import ApiProvider
            providers.append(ApiProvider(
                client=api_client,
                price_rules=price_rules,
            ))

        if network_provider is not None:
            providers.append(network_provider)

        if legacy_provider is not None:
            from backend.domain.acquisition.simple_dom_fallback import SimpleDomFallback
            providers.append(SimpleDomFallback(legacy_provider))

        if not providers:
            raise ValueError("V2 mode requires at least one provider")

        return FallbackChainProvider(providers)

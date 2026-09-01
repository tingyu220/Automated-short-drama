"""Native V2 链接采集 Composition Root。

组装 V2 Provider 链：NetworkProvider → SimpleDomFallback(LegacyDomProvider)，
返回 LinkAcquisitionService。

安全规则：
- 真实模式（page 可用）必须组装 V2 Provider 链
- 真实模式无 page → ConfigurationError
- Mock/Unit Test 模式（allow_legacy=True）允许 LegacyDomProvider 默认行为
"""
from __future__ import annotations

import logging
from typing import Any

from backend.application.services.link_acquisition_service import (
    LinkAcquisitionService,
    NullPromotionAssetRepository,
)
from backend.domain.acquisition.fallback_chain import FallbackChainProvider
from backend.domain.acquisition.promotion_asset_validator import (
    PromotionAssetValidator,
)
from backend.domain.acquisition.scoped_network_provider import ScopedNetworkProvider
from backend.domain.acquisition.simple_dom_fallback import SimpleDomFallback
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.platforms.tomato.providers.legacy_dom_provider import LegacyDomProvider
from backend.platforms.tomato.providers.network_provider import NetworkProvider
from backend.platforms.tomato.network.network_listener import NetworkListener

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """生产模式缺少必要组件。"""


def build_native_link_acquisition(
    *,
    tomato: Any,
    price_rules: list[TemplatePriceRule],
    page: Any | None = None,
    promotion_asset_repo: Any | None = None,
    allow_legacy: bool = False,
) -> LinkAcquisitionService:
    """组装 Native V2 链接采集服务。

    Args:
        tomato: TomatoAdapter（真实或 Mock）
        price_rules: 价格模板规则
        page: Playwright Page 对象（真实模式必须）
        promotion_asset_repo: 推广资产仓储
        allow_legacy: 允许 Legacy 默认行为（仅 Mock/Unit Test）

    Returns:
        LinkAcquisitionService 实例

    Raises:
        ConfigurationError: 真实模式缺 page 或不允许 Legacy 时
    """
    repo = promotion_asset_repo or NullPromotionAssetRepository()
    validator = PromotionAssetValidator()

    if page is None:
        if not allow_legacy:
            raise ConfigurationError(
                "真实生产模式必须提供 Playwright Page 对象以启用 V2 Acquisition"
            )
        logger.warning("Mock 模式：使用 LegacyDomProvider 作为默认 Provider")
        return LinkAcquisitionService(
            LegacyDomProvider(tomato, price_rules),
            validator,
            repo,
        )

    listener = NetworkListener(page)
    network_provider = NetworkProvider(listener, price_rules)
    legacy_provider = LegacyDomProvider(tomato, price_rules)

    scoped_provider = ScopedNetworkProvider(
        listener=listener,
        network_provider=network_provider,
        legacy_provider=legacy_provider,
    )

    logger.info("V2 Acquisition 组装完成: ScopedNetworkProvider (Network Query → DOM Create → Requery)")

    return LinkAcquisitionService(scoped_provider, validator, repo)

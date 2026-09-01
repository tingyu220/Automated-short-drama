"""番茄网络发现 Provider（Phase 5）。

包装 LegacyDomProvider，在其执行期间启动 Playwright 网络监听，
记录业务接口的脱敏响应，用于分析真实 API 结构。

本阶段只发现、不替代 DOM；结果与 Legacy 完全一致，
只是在 diagnostics 中附加网络发现信息。
"""
from __future__ import annotations

from typing import Any

from backend.domain.acquisition.acquisition_result import AcquisitionResult
from backend.domain.ports.adapters import TomatoAdapter
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.network.network_listener import NetworkListener
from backend.platforms.tomato.providers.legacy_dom_provider import LegacyDomProvider


class NetworkDiscoveryProvider:
    """Discovery 阶段 Provider：Legacy + 网络监听。

    - 结果与 LegacyDomProvider 完全一致（candidates / selected / missing）
    - diagnostics 中附加 network_discovery 信息
    - page 为 None 时跳过监听（兼容 dry_run / mock 环境）
    """

    def __init__(
        self,
        tomato: TomatoAdapter,
        price_rules: list[TemplatePriceRule],
        *,
        page: Any = None,
        platform_domain_keyword: str = "changdupingtai",
    ) -> None:
        self._legacy = LegacyDomProvider(tomato, price_rules)
        self._page = page
        self._domain_keyword = platform_domain_keyword

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """执行 Legacy 采集并同步监听网络响应。"""
        listener: NetworkListener | None = None

        # 只有真实 page 存在时才启动监听
        if self._page is not None:
            listener = NetworkListener(
                self._page,
                platform_domain_keyword=self._domain_keyword,
            )

        try:
            result = self._legacy.acquire(task)
        finally:
            if listener is not None:
                listener.stop()

        # 附加发现信息到 diagnostics
        discovery_info = _build_discovery_info(listener)
        new_diagnostics = dict(result.diagnostics)
        new_diagnostics["network_discovery"] = discovery_info

        return AcquisitionResult(
            status=result.status,
            expected_types=list(result.expected_types),
            candidates=list(result.candidates),
            selected=list(result.selected),
            missing=dict(result.missing),
            warnings=list(result.warnings),
            diagnostics=new_diagnostics,
        )


def _build_discovery_info(listener: NetworkListener | None) -> dict:
    """从 listener 构造 discovery 摘要字典。"""
    if listener is None:
        return {
            "provider": "NETWORK_DISCOVERY",
            "capture_count": 0,
            "endpoint_counts": {},
            "endpoint_types": [],
            "listener_attached": False,
            "note": "page 为 None，未启动网络监听",
        }
    summary = listener.summary()
    summary["provider"] = "NETWORK_DISCOVERY"
    summary["listener_attached"] = True
    return summary

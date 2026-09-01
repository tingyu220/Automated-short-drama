"""优选平台 MiniProgram 推广适配器。

M0-6: 接入 Network Discovery Provider，支持真实网络监听。
discover() 方法现在可以从 Playwright page 捕获真实接口响应。
ensure_promotion() 仍返回 NOT_IMPLEMENTED（M0 不做真实创建）。
"""
from __future__ import annotations

from typing import Any

from backend.miniprogram.domain.ports.adapters import (
    AdapterStatus,
    DiscoveredPromotion,
    DiscoveryResult,
    MiniProgramPromotionAdapter,
)
from backend.miniprogram.platforms.youxuan.providers.network_discovery_provider import (
    DiscoveryOutcome,
    YouxuanNetworkDiscoveryProvider,
)


class YouxuanMiniProgramAdapter:
    """优选平台 MiniProgram 推广适配器。

    M0 阶段：
    - discover(): 支持 Network Discovery，从真实浏览器捕获接口响应
    - query_existing(): M0 占位，返回空列表
    - ensure_promotion(): 返回 NOT_IMPLEMENTED（M0 不创建）
    """

    def __init__(
        self,
        page: Any = None,
        *,
        platform_domain_keyword: str = "youxuan",
        artifacts_root: str | None = None,
    ) -> None:
        self._page = page
        self._domain_keyword = platform_domain_keyword
        self._artifacts_root = artifacts_root

    def discover(self, context: object) -> DiscoveryResult:
        """执行 Network Discovery。

        M0-6 实现：如果有 page，则从已捕获的网络响应中提取发现信息。
        当前版本需要外部先操作页面触发接口，本方法只读取已捕获数据。

        Args:
            context: MiniProgramContext（M0 暂不使用，预留参数）

        Returns:
            DiscoveryResult
        """
        if self._page is None:
            return DiscoveryResult(
                status=AdapterStatus.NOT_IMPLEMENTED,
                error_message="无浏览器页面，无法执行 Network Discovery",
            )

        # M0 阶段：直接读取当前页面已有的网络捕获
        # 实际使用中，会先在页面上手动操作触发接口，再调用此方法收集
        provider = YouxuanNetworkDiscoveryProvider(
            self._page,
            platform_domain_keyword=self._domain_keyword,
            artifacts_root=self._artifacts_root,
        )
        provider.start_listening()
        # 注意：M0 这里立即停止只是演示流程
        # 真实使用时应该在页面操作完成后再调用 stop_and_collect
        outcome: DiscoveryOutcome = provider.stop_and_collect(
            task_id=getattr(context, "task_id", None),
            save_artifacts=True,
        )

        result = DiscoveryResult(
            status=outcome.status,
            drama_name=getattr(context, "drama_name", None),
            error_message=outcome.note if outcome.status != "SUCCESS" else None,
            raw_responses=[c.response_body for c in outcome.captures],
        )

        # 将 discovery 摘要附加到 diagnostics 风格的字段（通过 raw_responses 传递）
        return result

    def query_existing(
        self, context: object, tier: str
    ) -> list[DiscoveredPromotion]:
        """查询指定档位已存在的推广。

        M0 占位：Discovery 阶段暂不解析业务数据，
        真实解析需在确认接口结构后实现。
        """
        return []

    def ensure_promotion(
        self, context: object, tier: str
    ) -> tuple[str, DiscoveredPromotion | None]:
        """确保推⼴存在（M0 不实现真实创建）。"""
        return AdapterStatus.NOT_IMPLEMENTED, None


# 兼容类型检查：确认满足 Protocol
_: MiniProgramPromotionAdapter = YouxuanMiniProgramAdapter()

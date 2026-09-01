"""MiniProgram 推广适配器端口协议。

M0 只实现 discover() 和 query_existing()，
ensure_promotion() 返回 NOT_IMPLEMENTED。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class AdapterStatus:
    """适配器操作状态。"""

    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    FAILED = "FAILED"


@dataclass
class DiscoveredPromotion:
    """发现的推广信息。"""

    promotion_id: str
    title: str
    price_tier: str
    template_id: str | None = None
    template_name: str | None = None
    mini_program_path: str | None = None
    mini_program_link: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    """Network Discovery 结果。"""

    status: str
    promotions: list[DiscoveredPromotion] = field(default_factory=list)
    drama_name: str | None = None
    external_drama_id: str | None = None
    version_label: str | None = None
    error_message: str | None = None
    raw_responses: list[dict] = field(default_factory=list)


class MiniProgramPromotionAdapter(Protocol):
    """MiniProgram 推广适配器统一接口。

    未来各平台（优选等）实现此协议。
    M0 阶段只做只读发现，不执行真实创建。
    """

    def discover(self, context: object) -> DiscoveryResult:
        """执行 Network Discovery，返回发现结果。

        M0 阶段为只读操作：人工操作页面 + 程序监听 Network Response。
        """
        ...

    def query_existing(
        self, context: object, tier: str
    ) -> list[DiscoveredPromotion]:
        """查询指定价格档位已存在的推广。

        Args:
            context: MiniProgramContext
            tier: 价格档位，如 "2.9"

        Returns:
            已发现的推广列表，可能为空
        """
        ...

    def ensure_promotion(
        self, context: object, tier: str
    ) -> tuple[str, DiscoveredPromotion | None]:
        """确保指定档位的推⼴存在（不存在则创建）。

        M0 不实现，返回 NOT_IMPLEMENTED。

        Returns:
            (status, promotion) — status 见 AdapterStatus
        """
        ...

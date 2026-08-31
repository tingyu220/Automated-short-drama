"""链接准备阶段与可选运行终点。"""
from __future__ import annotations


class LinkStage:
    """链接准备阶段的稳定标识。"""

    WAITING_AVAILABLE_TIME = "WAITING_AVAILABLE_TIME"
    LINK_EXTRACTION = "LINK_EXTRACTION"
    DELIVERY_DRAMA = "DELIVERY_DRAMA"
    PROMOTION_CONFIG = "PROMOTION_CONFIG"
    LINK_READY = "LINK_READY"

    ORDER = (
        WAITING_AVAILABLE_TIME,
        LINK_EXTRACTION,
        DELIVERY_DRAMA,
        PROMOTION_CONFIG,
        LINK_READY,
    )


class RunTarget:
    """当前版本允许用户选择的运行终点。"""

    LINK_EXTRACTION = LinkStage.LINK_EXTRACTION
    LINK_READY = LinkStage.LINK_READY
    ALLOWED = frozenset({LINK_EXTRACTION, LINK_READY})

    @classmethod
    def validate(cls, target: str) -> str:
        if target not in cls.ALLOWED:
            raise ValueError(f"不支持的链接准备运行终点: {target}")
        return target

    @classmethod
    def reaches(cls, target: str, stage: str) -> bool:
        cls.validate(target)
        try:
            return LinkStage.ORDER.index(stage) <= LinkStage.ORDER.index(target)
        except ValueError as exc:
            raise ValueError(f"未知链接准备阶段: {stage}") from exc

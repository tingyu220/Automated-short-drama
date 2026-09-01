"""RevenuePolicy — 收费回传金币规则。

M0 只定义接口，不写具体规则。
未配置时返回 RULE_PENDING。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RevenuePolicyStatus:
    """规则状态。"""

    RULE_PENDING = "RULE_PENDING"
    READY = "READY"


@dataclass
class RevenuePolicyResult:
    """收费回传金币计算结果。"""

    status: str
    callback_coins: int | None = None
    reason: str = ""


class RevenuePolicy(Protocol):
    """收费回传金币规则接口。"""

    def resolve_callback_coins(
        self,
        context: object,
        drama_info: dict,
    ) -> RevenuePolicyResult:
        """根据上下文和剧目信息计算回传金币数。

        M0 未配置时返回 RULE_PENDING。
        """
        ...

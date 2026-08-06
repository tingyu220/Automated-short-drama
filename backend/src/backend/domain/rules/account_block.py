"""账户块结构与 V1 块常量。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccountRow:
    """飞书账户表一行的领域表示；drama_name 为空表示可用。"""

    row_number: int
    name: str
    cid: str
    group: str
    enabled: bool
    is_test: bool
    drama_name: str


@dataclass
class BlockDefinition:
    """账户块结构：连续行按组顺序与数量排列。"""

    block_type: str
    group_patterns: tuple[tuple[str, int], ...]


# 块结构 V1 写死；不写死物理行号、账户名称、CID。
IAA_BLOCK = ("IAA", (("B1", 3), ("B4", 3), ("B7", 3), ("BX", 1)))
IAP_BLOCK = ("IAP", (("B1-9.9", 3), ("B2-2.9", 3)))

BLOCK_DEFINITIONS = {
    IAA_BLOCK[0]: BlockDefinition(IAA_BLOCK[0], IAA_BLOCK[1]),
    IAP_BLOCK[0]: BlockDefinition(IAP_BLOCK[0], IAP_BLOCK[1]),
}

"""账户块分配服务：按表顺序寻找首个完整可用块并生成写入计划。"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.rules.account_block import (
    BLOCK_DEFINITIONS,
    AccountRow,
    BlockDefinition,
)


@dataclass
class BlockAllocation:
    """一个账户块的分配预览结果。"""

    block_type: str
    rows: list[AccountRow]
    cids: list[str]
    test_account_row: AccountRow | None
    write_plan: dict[int, dict] = field(default_factory=dict)


class AccountAllocationService:
    """纯领域/应用服务：只做扫描与计划，不读取或回写飞书账户表。"""

    def __init__(self, drama_name: str) -> None:
        self._drama_name = drama_name

    def find_iaa_block(
        self,
        rows: list[AccountRow],
        allocated_cids: set[str],
    ) -> BlockAllocation | None:
        """从表头向下找第一个完整可用 IAA 块。"""
        return self._find_block(rows, allocated_cids, BLOCK_DEFINITIONS["IAA"])

    def find_iap_block(
        self,
        rows: list[AccountRow],
        allocated_cids: set[str],
        required: set[str],
    ) -> BlockAllocation | None:
        """按模板组合找 IAP 块；双模板必须 6 行完整，否则返回 None。"""
        patterns: list[tuple[str, int]] = []
        if "9.9" in required:
            patterns.append(("B1-9.9", 3))
        if "2.9" in required:
            patterns.append(("B2-2.9", 3))
        if not patterns:
            return None
        definition = BlockDefinition("IAP", tuple(patterns))
        return self._find_block(rows, allocated_cids, definition)

    def _find_block(
        self,
        rows: list[AccountRow],
        allocated_cids: set[str],
        definition: BlockDefinition,
    ) -> BlockAllocation | None:
        """按表顺序滑动窗口，返回首个匹配连续行组成的完整块。"""
        block_size = sum(count for _, count in definition.group_patterns)
        for start in range(len(rows) - block_size + 1):
            block = rows[start : start + block_size]
            if not self._matches_pattern(block, definition, allocated_cids):
                continue
            test_row = self._pick_test_row(block)
            return BlockAllocation(
                block_type=definition.block_type,
                rows=block,
                cids=[row.cid for row in block],
                test_account_row=test_row,
                write_plan=self._build_write_plan(block, test_row),
            )
        return None

    @staticmethod
    def _matches_pattern(
        block: list[AccountRow],
        definition: BlockDefinition,
        allocated_cids: set[str],
    ) -> bool:
        """校验连续行严格按组顺序排列且全部可用。"""
        index = 0
        for group, count in definition.group_patterns:
            for _ in range(count):
                row = block[index]
                if (
                    row.group != group
                    or not row.enabled
                    or row.drama_name
                    or row.cid in allocated_cids
                ):
                    return False
                index += 1
        return index == len(block)

    @staticmethod
    def _pick_test_row(block: list[AccountRow]) -> AccountRow | None:
        """默认从启用且未标记的 B4 行中选第一个。"""
        for row in block:
            if row.group == "B4" and row.enabled and not row.is_test:
                return row
        return None

    def _build_write_plan(
        self,
        block: list[AccountRow],
        test_row: AccountRow | None,
    ) -> dict[int, dict]:
        """只生成待写入行的计划，绝不包含已占用行。"""
        plan: dict[int, dict] = {}
        for row in block:
            entry: dict[str, str | bool] = {"drama_name": self._drama_name}
            if test_row is not None and row.row_number == test_row.row_number:
                entry["is_test"] = True
            plan[row.row_number] = entry
        return plan

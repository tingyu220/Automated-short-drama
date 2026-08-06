"""账户块分配服务单元测试。"""
from __future__ import annotations

from backend.application.services.account_allocation_service import (
    AccountAllocationService,
)
from backend.domain.rules.account_block import AccountRow


def _row(
    row_number: int,
    name: str,
    cid: str,
    group: str,
    *,
    enabled: bool = True,
    is_test: bool = False,
    drama_name: str = "",
) -> AccountRow:
    return AccountRow(
        row_number=row_number,
        name=name,
        cid=cid,
        group=group,
        enabled=enabled,
        is_test=is_test,
        drama_name=drama_name,
    )


def _iaa_block(
    start: int,
    cid_prefix: str,
    *,
    enabled: bool = True,
    drama_name: str = "",
    marked_b4: tuple[int, ...] = (),
) -> list[AccountRow]:
    """按 B1x3 + B4x3 + B7x3 + BXx1 生成连续 IAA 块。"""
    groups = [("B1", 3), ("B4", 3), ("B7", 3), ("BX", 1)]
    rows: list[AccountRow] = []
    index = start
    for group, count in groups:
        for _ in range(count):
            rows.append(
                _row(
                    index,
                    f"{cid_prefix}-name-{index}",
                    f"cid-{cid_prefix}-{index}",
                    group,
                    enabled=enabled,
                    is_test=index in marked_b4 and group == "B4",
                    drama_name=drama_name,
                )
            )
            index += 1
    return rows


def _iap_block(
    start: int,
    cid_prefix: str,
    groups: tuple[str, ...] = ("B1-9.9", "B2-2.9"),
) -> list[AccountRow]:
    """按指定 IAP 组顺序生成连续块。"""
    rows: list[AccountRow] = []
    index = start
    for group in groups:
        for _ in range(3):
            rows.append(
                _row(
                    index,
                    f"{cid_prefix}-name-{index}",
                    f"cid-{cid_prefix}-{index}",
                    group,
                )
            )
            index += 1
    return rows


class TestFindIaaBlock:
    """IAA 块扫描与测试户挑选。"""

    def test_full_block_returns_ten_rows_and_first_free_b4(self):
        rows = _iaa_block(1, "iaa")
        allocation = AccountAllocationService("测试剧").find_iaa_block(rows, set())

        assert allocation is not None
        assert [row.row_number for row in allocation.rows] == list(range(1, 11))
        assert allocation.cids == [f"cid-iaa-{i}" for i in range(1, 11)]
        assert allocation.test_account_row is not None
        assert allocation.test_account_row.group == "B4"
        assert allocation.test_account_row.row_number == 4
        assert allocation.write_plan[4]["is_test"] is True

    def test_occupied_block_is_skipped(self):
        rows = _iaa_block(1, "a", drama_name="已占用剧") + _iaa_block(11, "b")
        allocation = AccountAllocationService("新剧").find_iaa_block(rows, set())

        assert allocation is not None
        assert [row.row_number for row in allocation.rows] == list(range(11, 21))

    def test_disabled_block_is_skipped(self):
        rows = _iaa_block(1, "a", enabled=False) + _iaa_block(11, "b")
        allocation = AccountAllocationService("新剧").find_iaa_block(rows, set())

        assert allocation is not None
        assert [row.row_number for row in allocation.rows] == list(range(11, 21))

    def test_block_with_allocated_cid_is_skipped(self):
        rows = _iaa_block(1, "a") + _iaa_block(11, "b")
        allocation = AccountAllocationService("新剧").find_iaa_block(
            rows, {"cid-a-1"}
        )

        assert allocation is not None
        assert [row.row_number for row in allocation.rows] == list(range(11, 21))

    def test_wrong_group_order_is_not_an_iaa_block(self):
        rows = _iaa_block(1, "ok")
        rows[2], rows[3] = rows[3], rows[2]  # B1 与 B4 交换错序
        allocation = AccountAllocationService("测试剧").find_iaa_block(rows, set())

        assert allocation is None

    def test_test_account_skips_already_marked_b4(self):
        rows = _iaa_block(1, "iaa", marked_b4=(4,))
        allocation = AccountAllocationService("测试剧").find_iaa_block(rows, set())

        assert allocation is not None
        assert allocation.test_account_row is not None
        assert allocation.test_account_row.row_number == 5
        assert allocation.write_plan[5]["is_test"] is True
        assert "is_test" not in allocation.write_plan[4]


class TestFindIapBlock:
    """IAP 块按模板组合扫描。"""

    def test_dual_template_returns_six_rows(self):
        rows = _iap_block(1, "iap")
        allocation = AccountAllocationService("测试剧").find_iap_block(
            rows, set(), {"9.9", "2.9"}
        )

        assert allocation is not None
        assert [row.group for row in allocation.rows] == [
            "B1-9.9",
            "B1-9.9",
            "B1-9.9",
            "B2-2.9",
            "B2-2.9",
            "B2-2.9",
        ]
        assert allocation.cids == [f"cid-iap-{i}" for i in range(1, 7)]

    def test_only_9_9_returns_three_rows(self):
        rows = _iap_block(1, "iap", groups=("B1-9.9",))
        allocation = AccountAllocationService("测试剧").find_iap_block(
            rows, set(), {"9.9"}
        )

        assert allocation is not None
        assert [row.group for row in allocation.rows] == ["B1-9.9"] * 3

    def test_only_2_9_returns_three_rows(self):
        rows = _iap_block(1, "iap", groups=("B2-2.9",))
        allocation = AccountAllocationService("测试剧").find_iap_block(
            rows, set(), {"2.9"}
        )

        assert allocation is not None
        assert [row.group for row in allocation.rows] == ["B2-2.9"] * 3

    def test_dual_template_with_partial_group_returns_none(self):
        rows = _iap_block(1, "iap", groups=("B1-9.9",))
        allocation = AccountAllocationService("测试剧").find_iap_block(
            rows, set(), {"9.9", "2.9"}
        )

        assert allocation is None

    def test_wrong_group_order_is_not_an_iap_block(self):
        rows = _iap_block(1, "a", groups=("B2-2.9", "B1-9.9"))
        allocation = AccountAllocationService("测试剧").find_iap_block(
            rows, set(), {"9.9", "2.9"}
        )

        assert allocation is None


class TestWritePlan:
    """写入计划只覆盖待写入行。"""

    def test_write_plan_contains_only_pending_rows(self):
        rows = _iaa_block(1, "a", drama_name="已占用剧") + _iaa_block(11, "b")
        allocation = AccountAllocationService("新剧").find_iaa_block(rows, set())

        assert allocation is not None
        assert sorted(allocation.write_plan) == list(range(11, 21))
        assert all(
            item["drama_name"] == "新剧"
            for item in allocation.write_plan.values()
        )

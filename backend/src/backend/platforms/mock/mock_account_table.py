"""共享 Mock 账户表：已占用行 + 完整 IAA/IAP 块，供 API 与 Worker 使用。"""
from __future__ import annotations

from backend.domain.rules.account_block import AccountRow


def _build_mock_account_rows() -> list[AccountRow]:
    """构造内存 Mock 账户表：已占用行 + 完整 IAA/IAP 块。"""
    rows: list[AccountRow] = []
    for index in range(1, 4):
        rows.append(
            AccountRow(
                row_number=len(rows) + 1,
                name=f"已占-B1-{index}",
                cid=f"MOCK-CID-OCCUPIED-IAA-{index}",
                group="B1",
                enabled=True,
                is_test=False,
                drama_name="已占用剧A",
            )
        )
    for index, group in enumerate(
        ("B1", "B1", "B1", "B4", "B4", "B4", "B7", "B7", "B7", "BX"),
        start=1,
    ):
        rows.append(
            AccountRow(
                row_number=len(rows) + 1,
                name=f"IAA-{group}-{index}",
                cid=f"MOCK-CID-IAA-{index}",
                group=group,
                enabled=True,
                is_test=False,
                drama_name="",
            )
        )
    for index, group in enumerate(
        ("B1-9.9", "B1-9.9", "B1-9.9", "B2-2.9", "B2-2.9", "B2-2.9"),
        start=1,
    ):
        rows.append(
            AccountRow(
                row_number=len(rows) + 1,
                name=f"IAP-{group}-{index}",
                cid=f"MOCK-CID-IAP-{index}",
                group=group,
                enabled=True,
                is_test=False,
                drama_name="",
            )
        )
    for index in range(1, 4):
        rows.append(
            AccountRow(
                row_number=len(rows) + 1,
                name=f"已占-IAP-{index}",
                cid=f"MOCK-CID-OCCUPIED-IAP-{index}",
                group="B1-9.9",
                enabled=True,
                is_test=False,
                drama_name="已占用剧B",
            )
        )
    return rows


MOCK_ACCOUNT_ROWS: list[AccountRow] = _build_mock_account_rows()

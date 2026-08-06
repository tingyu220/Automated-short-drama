"""账户 API 路由：V1 使用内存 Mock 账户表，仅提供概览与分配预览。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.application.services.account_allocation_service import (
    AccountAllocationService,
    BlockAllocation,
)
from backend.domain.rules.account_block import AccountRow
from backend.interfaces.api.schemas import AccountOverviewView

router = APIRouter(tags=["accounts"])


class _AllocatePreviewRequest(BaseModel):
    """分配预览请求体。"""

    drama_name: str = Field(min_length=1)
    block_type: Literal["IAA", "IAP"]
    allocated_cids: list[str] = []


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


MOCK_ACCOUNT_ROWS = _build_mock_account_rows()


def _account_summary(row: AccountRow) -> dict:
    """账户行摘要：row/name/cid/group/enabled/is_test/drama_name。"""
    return {
        "row": row.row_number,
        "name": row.name,
        "cid": row.cid,
        "group": row.group,
        "enabled": row.enabled,
        "is_test": row.is_test,
        "drama_name": row.drama_name,
    }


def _allocation_payload(allocation: BlockAllocation) -> dict:
    """分配预览响应：块行、CID 与写入计划。"""
    return {
        "found": True,
        "block_type": allocation.block_type,
        "rows": [_account_summary(row) for row in allocation.rows],
        "cids": allocation.cids,
        "test_account_row": (
            _account_summary(allocation.test_account_row)
            if allocation.test_account_row is not None
            else None
        ),
        "write_plan": {
            str(row_number): entry
            for row_number, entry in allocation.write_plan.items()
        },
    }


def _find_allocation(
    service: AccountAllocationService,
    block_type: str,
    allocated_cids: list[str],
) -> BlockAllocation | None:
    """按块类型在 Mock 表中查找首个可用块。"""
    allocated = set(allocated_cids)
    if block_type == "IAA":
        return service.find_iaa_block(MOCK_ACCOUNT_ROWS, allocated)
    if block_type == "IAP":
        return service.find_iap_block(
            MOCK_ACCOUNT_ROWS, allocated, {"9.9", "2.9"}
        )
    return None


@router.get("/accounts/overview", response_model=AccountOverviewView)
def account_overview() -> AccountOverviewView:
    """返回内存 Mock 账户概览。"""
    return AccountOverviewView(
        sync_status="mock",
        last_synced_at=datetime.now(timezone.utc),
        accounts=[_account_summary(row) for row in MOCK_ACCOUNT_ROWS],
    )


@router.post("/accounts/allocate-preview")
def allocate_preview(payload: _AllocatePreviewRequest) -> dict:
    """预览首个可用账户块；只返回计划，不写入任何数据。"""
    service = AccountAllocationService(payload.drama_name)
    allocation = _find_allocation(
        service, payload.block_type, payload.allocated_cids
    )
    if allocation is None:
        return {"found": False}
    return _allocation_payload(allocation)

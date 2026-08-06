"""账户 API 路由：V1 仅返回 not_configured 占位。"""
from __future__ import annotations

from fastapi import APIRouter

from backend.interfaces.api.schemas import AccountOverviewView

router = APIRouter(tags=["accounts"])


@router.get("/accounts/overview", response_model=AccountOverviewView)
def account_overview() -> AccountOverviewView:
    """返回账户概览；真实飞书同步在 Phase 7 接入后替换。"""
    return AccountOverviewView(
        sync_status="not_configured",
        last_synced_at=None,
        accounts=[],
    )

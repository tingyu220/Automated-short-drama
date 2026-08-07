"""投放系统配置快照 API（只读展示，不触发远程写操作）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.application.services.delivery_config_service import (
    DeliveryConfigSnapshotService,
)

router = APIRouter(tags=["delivery-config"])
_service = DeliveryConfigSnapshotService()


def _guard(exc: FileNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


class MappingProposalBody(BaseModel):
    """用户编辑后的 CID 映射列表。"""

    rows: list[dict]


@router.get("/config/delivery/summary")
def delivery_config_summary() -> dict:
    try:
        return _service.summary()
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.get("/config/delivery/cids")
def delivery_config_cids() -> dict:
    try:
        rows = _service.cids()
        return {"rows": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.get("/config/delivery/ad-presets")
def delivery_config_ad_presets() -> dict:
    try:
        rows = _service.ad_presets()
        return {"rows": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.get("/config/delivery/open-presets")
def delivery_config_open_presets() -> dict:
    try:
        rows = _service.open_presets()
        return {"rows": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.get("/config/delivery/product-libraries")
def delivery_config_product_libraries() -> dict:
    try:
        rows = _service.product_libraries()
        return {"rows": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.get("/config/delivery/accounts")
def delivery_config_accounts() -> dict:
    try:
        rows = _service.accounts()
        return {"rows": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.get("/config/delivery/mapping-proposal")
def delivery_config_mapping_proposal() -> dict:
    try:
        rows = _service.mapping_proposal()
        return {"rows": rows, "count": len(rows)}
    except FileNotFoundError as exc:
        raise _guard(exc) from exc


@router.put("/config/delivery/mapping-proposal")
def save_delivery_mapping_proposal(body: MappingProposalBody) -> dict:
    """保存面板编辑后的 CID 映射，覆盖自动同步默认值。"""
    try:
        payload = _service.save_mapping_proposal(body.rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise _guard(exc) from exc
    return {
        "saved_at": payload.get("saved_at"),
        "count": len(payload.get("rows", [])),
    }

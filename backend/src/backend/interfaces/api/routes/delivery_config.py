"""投放系统配置快照 API（只读展示，不触发远程写操作）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.application.services.delivery_config_service import (
    DeliveryConfigSnapshotService,
)

router = APIRouter(tags=["delivery-config"])
_service = DeliveryConfigSnapshotService()


def _guard(exc: FileNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


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

"""投放系统配置快照 API 集成测试。"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.application.services.delivery_config_service import (
    DeliveryConfigSnapshotService,
)
from backend.interfaces.api.main import create_app
from backend.interfaces.api.routes import delivery_config as delivery_route


def _write_snapshot(tmp_path) -> None:
    (tmp_path / "delivery_snapshot.json").write_text(
        json.dumps(
            {
                "counts": {"cid": 1, "ad_presets": 1, "open_presets": 1},
                "extracted_at": "2026-08-07T00:00:00+00:00",
                "cid_groups": [{"cid": "c1", "group": "B1"}],
                "ad_presets": [{"id": 1, "preview_name": "p1"}],
                "open_presets": [{"id": 2, "preset_name": "o1"}],
                "product_libraries": [],
                "mapping_proposal": [{"cid": "c1"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "delivery_accounts.json").write_text(
        json.dumps({"rows": [{"fiAdvertiserId": 1}]}), encoding="utf-8"
    )


def test_delivery_config_endpoints(tmp_path, monkeypatch):
    _write_snapshot(tmp_path)
    service = DeliveryConfigSnapshotService(extracted_dir=tmp_path)
    monkeypatch.setattr(delivery_route, "_service", service)
    client = TestClient(create_app(dist_dir=None))

    summary = client.get("/api/config/delivery/summary")
    cids = client.get("/api/config/delivery/cids")
    presets = client.get("/api/config/delivery/ad-presets")
    proposal = client.get("/api/config/delivery/mapping-proposal")

    assert summary.status_code == 200
    assert summary.json()["counts"]["cid"] == 1
    assert cids.json()["count"] == 1
    assert presets.json()["count"] == 1
    assert proposal.json()["count"] == 1


def test_delivery_config_missing_snapshot_returns_404(tmp_path, monkeypatch):
    service = DeliveryConfigSnapshotService(extracted_dir=tmp_path)
    monkeypatch.setattr(delivery_route, "_service", service)
    client = TestClient(create_app(dist_dir=None))

    response = client.get("/api/config/delivery/summary")

    assert response.status_code == 404
    assert "采集脚本" in response.json()["detail"]

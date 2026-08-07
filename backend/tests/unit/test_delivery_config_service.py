"""投放系统配置快照服务测试。"""
from __future__ import annotations

import json

import pytest

from backend.application.services.delivery_config_service import (
    DeliveryConfigSnapshotService,
)


def _write_snapshot(tmp_path) -> None:
    snapshot = {
        "counts": {
            "cid": 2,
            "ad_presets": 1,
            "open_presets": 1,
            "product_libraries": 1,
            "accounts": 2,
        },
        "extracted_at": "2026-08-07T00:00:00+00:00",
        "cid_groups": [{"cid": "端iaa-漫爵涛爆新b1", "group": "B1"}],
        "ad_presets": [{"id": 1, "preview_name": "1-iaa漫剧"}],
        "open_presets": [{"id": 2, "preset_name": "端免-爵涛-老户"}],
        "product_libraries": [{"cid": "端iaa-漫爵涛爆新b1"}],
        "mapping_proposal": [{"cid": "端iaa-漫爵涛爆新b1"}],
    }
    (tmp_path / "delivery_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "delivery_accounts.json").write_text(
        json.dumps({"rows": [{"fiAdvertiserId": 1}]}), encoding="utf-8"
    )


def test_service_reads_snapshot(tmp_path):
    _write_snapshot(tmp_path)
    service = DeliveryConfigSnapshotService(extracted_dir=tmp_path)

    assert service.summary()["counts"]["cid"] == 2
    assert service.cids()[0]["group"] == "B1"
    assert service.ad_presets()[0]["preview_name"] == "1-iaa漫剧"
    assert service.accounts() == [{"fiAdvertiserId": 1}]
    assert len(service.mapping_proposal()) == 1


def test_service_raises_when_snapshot_missing(tmp_path):
    service = DeliveryConfigSnapshotService(extracted_dir=tmp_path)

    with pytest.raises(FileNotFoundError):
        service.summary()


def test_save_mapping_proposal_overrides_snapshot(tmp_path):
    _write_snapshot(tmp_path)
    service = DeliveryConfigSnapshotService(extracted_dir=tmp_path)
    row = service.mapping_proposal()[0]
    row["ad_preset"] = "手动广告预设"

    saved = service.save_mapping_proposal([row])

    assert saved["count"] == 1
    assert service.mapping_proposal()[0]["ad_preset"] == "手动广告预设"

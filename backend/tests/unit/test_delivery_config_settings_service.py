"""投放系统配置设置服务测试。"""
from __future__ import annotations

import json

from backend.application.services.delivery_config_settings_service import (
    DeliveryConfigSettingsService,
)


def _write_snapshot(tmp_path) -> None:
    (tmp_path / "delivery_snapshot.json").write_text(
        json.dumps(
            {
                "ad_presets": [
                    {
                        "id": 1,
                        "preview_name": "1-iaa漫剧",
                        "project_name": "<平台方>#端免<剧名称><日期>bxr-x",
                        "ad_name": "<平台方>#端免<剧名称><日期>bxr-x",
                    }
                ],
                "open_presets": [
                    {"id": 2, "preset_name": "端免-爵涛-老户"}
                ],
                "mapping_proposal": [
                    {"cid": "c1", "douyin_account": "43242208659"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "delivery_accounts.json").write_text(
        json.dumps({"rows": [{"ownerUserName": "B组田雨"}]}),
        encoding="utf-8",
    )


def test_settings_defaults_and_options(tmp_path):
    _write_snapshot(tmp_path)
    service = DeliveryConfigSettingsService(extracted_dir=tmp_path)

    settings = service.get_settings()

    assert settings["values"]["douyin"]["douyin_account"] == "43242208659"
    assert settings["options"]["account_owners"] == ["B组田雨"]
    assert settings["options"]["naming_templates"]


def test_save_settings_overrides_defaults(tmp_path):
    _write_snapshot(tmp_path)
    service = DeliveryConfigSettingsService(extracted_dir=tmp_path)

    service.save_settings(
        {"douyin": {"douyin_account": "123456"}, "runtime": {"price_tiers": "3.9"}}
    )

    settings = service.get_settings()
    assert settings["values"]["douyin"]["douyin_account"] == "123456"
    assert settings["values"]["runtime"]["price_tiers"] == "3.9"
    assert settings["values"]["link"]["iaa_episode_threshold"] == 50

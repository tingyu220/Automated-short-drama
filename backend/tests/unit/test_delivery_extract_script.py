"""投放系统配置采集脚本的纯函数测试。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "extract-delivery-config.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "extract_delivery_config_test", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = _load_module()


def test_infer_group_from_cid_suffix():
    assert module._infer_group("端iaa-漫爵涛爆新b1") == "B1"
    assert module._infer_group("端iaa-漫爵涛爆新b4") == "B4"
    assert module._infer_group("端iaa-漫爵涛爆新b7") == "B7"
    assert module._infer_group("端iaa-漫爵涛爆新bx") == "BX"
    assert module._infer_group("端iap-漫花海爆新b2") == "B2"


def test_candidate_ad_preset_by_group():
    module = _load_module()
    base = {"preview_name": "1-iaa漫剧-短剧漫剧库（新美）一零五-一万预算"}

    assert module._candidate_ad_preset(
        {**base, "_group": "B1", "_is_iap": False}
    ) is True
    assert module._candidate_ad_preset(
        {**base, "_group": "B4", "_is_iap": False}
    ) is False


def test_candidate_ad_preset_iap():
    module = _load_module()

    assert module._candidate_ad_preset(
        {
            "preview_name": "付费10全-短剧库-1系数-冰依好剧",
            "_group": "B1",
            "_is_iap": True,
        }
    ) is True
    assert module._candidate_ad_preset(
        {
            "preview_name": "付费3全-短剧库-1系数-剧变漫剧",
            "_group": "B2",
            "_is_iap": True,
        }
    ) is True
    assert module._candidate_ad_preset(
        {
            "preview_name": "1-iaa漫剧-短剧漫剧库（新美）一零五-一万预算",
            "_group": "B1",
            "_is_iap": True,
        }
    ) is False

"""投放系统配置设置服务：默认值 + 面板编辑持久化。"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.infrastructure.config.settings import Settings


class DeliveryConfigSettingsService:
    """读取投放系统同步数据生成可编辑配置，面板修改写入本地覆盖文件。"""

    def __init__(self, extracted_dir: Path | None = None) -> None:
        self._dir = extracted_dir or (Settings().data_dir / "extracted")

    def get_settings(self) -> dict:
        snapshot = self._read_snapshot()
        accounts = self._read_accounts()
        defaults = self._build_defaults(snapshot, accounts)
        edits = self._load_edits()
        return {
            "values": _deep_merge(defaults, edits.get("values") or {}),
            "options": self._build_options(snapshot, accounts),
            "saved_at": edits.get("saved_at"),
        }

    def save_settings(self, values: dict) -> dict:
        snapshot = self._read_snapshot()
        accounts = self._read_accounts()
        defaults = self._build_defaults(snapshot, accounts)
        merged = _deep_merge(defaults, values)
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "count": len(merged),
            "values": merged,
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._edits_path()
        fd, tmp = tempfile.mkstemp(
            dir=str(self._dir), suffix=".json", text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return payload

    def _read_snapshot(self) -> dict:
        path = self._dir / "delivery_snapshot.json"
        if not path.exists():
            raise FileNotFoundError("投放系统配置快照不存在，请先运行采集脚本")
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_accounts(self) -> list[dict]:
        path = self._dir / "delivery_accounts.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("rows", [])

    def _edits_path(self) -> Path:
        return self._dir / "delivery_settings_edits.json"

    def _load_edits(self) -> dict:
        path = self._edits_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _build_defaults(snapshot: dict, accounts: list[dict]) -> dict:
        mapping = snapshot.get("mapping_proposal") or []
        douyin_values = sorted(
            {
                str(row.get("douyin_account") or "")
                for row in mapping
                if row.get("douyin_account")
            }
        )
        owners = sorted(
            {
                str(row.get("ownerUserName") or "")
                for row in accounts
                if row.get("ownerUserName")
            }
        )
        templates = _naming_templates(snapshot)
        return {
            "link": {
                "iaa_episode_threshold": 50,
                "iap_2_9_target": 2.9,
                "iap_2_9_min": 2.6,
                "iap_2_9_max": 5.0,
                "iap_9_9_target": 9.9,
                "iap_9_9_min": 8.8,
                "iap_9_9_max": 13.8,
                "same_distance_strategy": "HIGHER_PRICE_FIRST",
            },
            "douyin": {
                "douyin_account": douyin_values[-1] if douyin_values else ""
            },
            "platform": {
                "delivery_base_url": "http://web.tjhaozew.top",
                "ocean_base_url": "https://business.oceanengine.com",
                "tomato_base_url": "https://www.changdupingtai.com",
            },
            "naming": {
                "iaa_project_template": _first_contains(
                    templates, ("bxr", "端免")
                ),
                "iap_project_template": _first_contains(
                    templates, ("ubr", "端付")
                ),
                "test_project_template": _first_contains(templates, ("cbo",)),
            },
            "runtime": {
                "scan_interval_seconds": 3600,
                "login_wait_seconds": 600,
                "price_tiers": "2.9, 9.9",
                "material_group_cap": 30,
                "max_project_count": 3,
            },
            "account": {
                "account_owner": owners[0] if owners else "B组田雨",
                "test_account_source": "IAA_B4",
            },
        }

    @staticmethod
    def _build_options(snapshot: dict, accounts: list[dict]) -> dict:
        ad_presets = snapshot.get("ad_presets") or []
        open_presets = snapshot.get("open_presets") or []
        mapping = snapshot.get("mapping_proposal") or []
        owners = sorted(
            {
                str(row.get("ownerUserName") or "")
                for row in accounts
                if row.get("ownerUserName")
            }
        )
        douyin_values = sorted(
            {
                str(row.get("douyin_account") or "")
                for row in mapping
                if row.get("douyin_account")
            }
        )
        return {
            "ad_preset_names": _unique_values(
                (row.get("preview_name") for row in ad_presets)
            ),
            "open_preset_names": _unique_values(
                (row.get("preset_name") for row in open_presets)
            ),
            "naming_templates": _naming_templates(snapshot),
            "douyin_accounts": douyin_values,
            "account_owners": owners,
        }


def _naming_templates(snapshot: dict) -> list[str]:
    templates: list[str] = []
    seen: set[str] = set()
    for preset in snapshot.get("ad_presets") or []:
        for key in ("project_name", "ad_name"):
            value = str(preset.get(key) or "").strip()
            if value and "<" in value and value not in seen:
                seen.add(value)
                templates.append(value)
    return templates


def _unique_values(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _first_contains(values: list[str], markers: tuple[str, ...]) -> str:
    for value in values:
        if any(marker in value for marker in markers):
            return value
    return values[0] if values else ""


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged

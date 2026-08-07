"""投放系统配置快照读取服务（只读，不写远程）。"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.infrastructure.config.settings import Settings


class DeliveryConfigSnapshotService:
    """读取 data/extracted 下由采集脚本生成的投放系统配置快照。"""

    def __init__(self, extracted_dir: Path | None = None) -> None:
        self._dir = extracted_dir or (Settings().data_dir / "extracted")

    def summary(self) -> dict:
        snapshot = self._read("delivery_snapshot.json")
        return {
            "counts": snapshot.get("counts", {}),
            "extracted_at": snapshot.get("extracted_at"),
            "mapping_proposal_count": len(
                snapshot.get("mapping_proposal", [])
            ),
        }

    def cids(self) -> list[dict]:
        return self._read("delivery_snapshot.json").get("cid_groups", [])

    def ad_presets(self) -> list[dict]:
        return self._read("delivery_snapshot.json").get("ad_presets", [])

    def open_presets(self) -> list[dict]:
        return self._read("delivery_snapshot.json").get("open_presets", [])

    def product_libraries(self) -> list[dict]:
        return self._read("delivery_snapshot.json").get(
            "product_libraries", []
        )

    def accounts(self) -> list[dict]:
        return self._read("delivery_accounts.json").get("rows", [])

    def mapping_proposal(self) -> list[dict]:
        base = self._read("delivery_snapshot.json").get(
            "mapping_proposal", []
        )
        edits = self._load_edits()
        if not edits:
            return base
        merged = []
        for row in base:
            edited = edits.get(str(row.get("cid", "")))
            merged.append(edited if edited is not None else row)
        for edited in edits.values():
            if edited.get("cid") not in {row.get("cid") for row in merged}:
                merged.append(edited)
        return merged

    def save_mapping_proposal(self, rows: list[dict]) -> dict:
        """保存用户在面板上的 CID 映射修改，覆盖自动同步默认值。"""
        if not rows:
            raise ValueError("CID 映射不能为空")
        cleaned = []
        for row in rows:
            cid = str(row.get("cid") or "").strip()
            if not cid:
                continue
            cleaned.append(
                {
                    "cid": cid,
                    "group": str(row.get("group") or ""),
                    "company": str(row.get("company") or ""),
                    "pay_type": row.get("pay_type"),
                    "account_count": int(row.get("account_count") or 0),
                    "ad_preset": str(row.get("ad_preset") or ""),
                    "open_preset": str(row.get("open_preset") or ""),
                    "douyin_account": str(row.get("douyin_account") or ""),
                    "ad_preset_candidates": list(
                        row.get("ad_preset_candidates") or []
                    ),
                    "open_preset_candidates": list(
                        row.get("open_preset_candidates") or []
                    ),
                }
            )
        if not cleaned:
            raise ValueError("CID 映射至少需要一条有效记录")
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "count": len(cleaned),
            "rows": cleaned,
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

    def _read(self, filename: str) -> dict:
        path = self._dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"投放系统配置快照不存在: {path}，请先运行采集脚本"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _edits_path(self) -> Path:
        return self._dir / "delivery_mapping_edits.json"

    def _load_edits(self) -> dict[str, dict]:
        path = self._edits_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data.get("rows") or []
            return {str(row.get("cid", "")): row for row in rows if row.get("cid")}
        except (OSError, json.JSONDecodeError):
            return {}

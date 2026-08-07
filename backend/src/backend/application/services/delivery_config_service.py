"""投放系统配置快照读取服务（只读，不写远程）。"""
from __future__ import annotations

import json
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
        return self._read("delivery_snapshot.json").get(
            "mapping_proposal", []
        )

    def _read(self, filename: str) -> dict:
        path = self._dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"投放系统配置快照不存在: {path}，请先运行采集脚本"
            )
        return json.loads(path.read_text(encoding="utf-8"))

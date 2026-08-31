"""投放系统 Adapter Mock 实现 —— 内存态幂等资源与确定性任务状态."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.application.services.plan_rules import build_promotion_config_name
from backend.domain.ports.adapters import DeliverySystemAdapter, DramaAsset


class MockDeliverySystemAdapter(DeliverySystemAdapter):
    """确定性投放系统 Mock."""

    def __init__(self, poll_rounds_before_completed: int = 1):
        if poll_rounds_before_completed < 1:
            raise ValueError("poll_rounds_before_completed 必须 >= 1")
        self.poll_rounds_before_completed = poll_rounds_before_completed
        self._assets: dict[tuple[str, str], DramaAsset] = {}
        self._poll_counts: dict[str, int] = {}

    def find_or_create_drama_asset(self, drama_name: str, link: str) -> DramaAsset:
        key = (drama_name, link)
        existing = self._assets.get(key)
        if existing is not None:
            return existing
        digest = hashlib.sha256(f"{drama_name}|{link}".encode("utf-8")).hexdigest()[:12]
        asset = DramaAsset(
            delivery_drama_id=f"dd-{digest}",
            drama_name=drama_name,
            link=link,
        )
        self._assets[key] = asset
        return asset

    def ensure_promotion_config(
        self,
        asset_id: str,
        link_type: str,
        link: str,
        drama_name: str,
        platform: str,
    ) -> str:
        del asset_id, link  # Mock 无需真实资源/链接内容
        return build_promotion_config_name(link_type, platform, drama_name)

    def submit_plan(self, plan_spec: Any) -> str:
        return f"task-{self._digest(plan_spec)}"

    def poll_task_status(self, external_task_id: str) -> str:
        count = self._poll_counts.get(external_task_id, 0)
        self._poll_counts[external_task_id] = count + 1
        return "SUBMITTED" if count < self.poll_rounds_before_completed else "COMPLETED"

    def find_task_by_idempotency_key(self, task_name: str) -> str | None:
        """Mock 提交确定成功，不产生结果不确定对账项。"""
        return None

    @staticmethod
    def _digest(value: Any) -> str:
        try:
            payload = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload = repr(value)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

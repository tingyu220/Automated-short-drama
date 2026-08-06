"""投放系统与巨量产品库编排服务."""
from __future__ import annotations

import time
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError, ValidationError
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import (
    DeliverySystemAdapter,
    DramaAsset,
    OceanEngineAdapter,
)


class DeliveryFlowService:
    """编排剧目资源、推广配置、巨量产品库与计划提交。"""

    def __init__(
        self,
        delivery: DeliverySystemAdapter,
        ocean: OceanEngineAdapter,
    ) -> None:
        self._delivery = delivery
        self._ocean = ocean

    def ensure_drama_asset(self, drama_name: str, link: str) -> DramaAsset:
        """识别或创建投放系统剧目资源，幂等。"""
        return self._delivery.find_or_create_drama_asset(drama_name, link)

    def ensure_promotion_config(
        self,
        asset: DramaAsset,
        link_type: str,
        link: str,
        platform: str,
    ) -> str:
        """创建缺失的推广内容配置并返回配置 ID。"""
        return self._delivery.ensure_promotion_config(
            asset.delivery_drama_id,
            link_type,
            link,
            asset.drama_name,
            platform,
        )

    def create_product(self, album_id: str, fields: dict[str, Any]) -> str:
        """创建巨量产品并校验创建结果。"""
        product_id = self._ocean.create_product(album_id, fields)
        if not self._ocean.verify_product(product_id):
            raise ExternalAdapterError(f"巨量产品创建后校验失败: {product_id}")
        return product_id

    def submit_plan(self, plan_spec: PlanSpec) -> str:
        """校验计划规格并委托投放系统提交，返回外部任务 ID。"""
        if not plan_spec.link_set:
            raise ValidationError("PlanSpec 至少需要 1 条推广链接")
        if not plan_spec.account_cids:
            raise ValidationError("PlanSpec 至少需要 1 个 CID")
        return self._delivery.submit_plan(plan_spec)

    def poll_until_completed(
        self,
        external_task_id: str,
        max_polls: int = 24,
        interval_seconds: int = 0,
    ) -> str:
        """轮询任务状态，COMPLETED 立即返回，超过 max_polls 返回 TIMEOUT。"""
        for _ in range(max_polls):
            status = self._delivery.poll_task_status(external_task_id)
            if status == "COMPLETED":
                return status
            if interval_seconds > 0:
                time.sleep(interval_seconds)
        return "TIMEOUT"

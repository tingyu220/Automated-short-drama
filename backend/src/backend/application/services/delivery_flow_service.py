"""投放系统与巨量产品库编排服务."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError, ValidationError
from backend.domain.plans.delivery_form_spec import DeliveryFormSpec
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

    def submit_plan(self, plan_spec: PlanSpec | DeliveryFormSpec) -> str:
        """校验计划规格并委托投放系统提交，返回外部任务 ID。"""
        if isinstance(plan_spec, DeliveryFormSpec):
            if not plan_spec.cid_rows:
                raise ValidationError("DeliveryFormSpec 至少需要 1 个 CID")
            if not plan_spec.material_ids:
                raise ValidationError("DeliveryFormSpec 至少需要 1 条素材")
            return self._delivery.submit_plan(plan_spec)
        if not plan_spec.link_set:
            raise ValidationError("PlanSpec 至少需要 1 条推广链接")
        if not plan_spec.account_cids:
            raise ValidationError("PlanSpec 至少需要 1 个 CID")
        return self._delivery.submit_plan(plan_spec)

    def find_task_by_idempotency_key(self, task_name: str) -> str | None:
        """按唯一任务名称对账，防止结果不确定时重复提交。"""
        return self._delivery.find_task_by_idempotency_key(task_name)

    def poll_until_completed(
        self,
        external_task_id: str,
        max_polls: int | None = None,
        interval_seconds: int = 0,
        *,
        poll_interval_seconds: int = 300,
        timeout_seconds: int = 7200,
        heartbeat_interval_seconds: int = 30,
        on_wait: Callable[[], None] | None = None,
        now_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> str:
        """按生产截止时间轮询；max_polls 仅保留给旧测试/调用兼容。"""
        if max_polls is not None:
            for _ in range(max_polls):
                status = self._delivery.poll_task_status(external_task_id)
                if status == "COMPLETED":
                    return status
                if interval_seconds > 0:
                    sleep_fn(interval_seconds)
            return "TIMEOUT"

        if (
            poll_interval_seconds <= 0
            or timeout_seconds <= 0
            or heartbeat_interval_seconds <= 0
        ):
            raise ValueError("轮询间隔和超时必须为正数")
        deadline = now_fn() + timeout_seconds
        while now_fn() < deadline:
            status = self._delivery.poll_task_status(external_task_id)
            if status == "COMPLETED":
                return status
            remaining = deadline - now_fn()
            if remaining <= 0:
                break
            wait_seconds = min(float(poll_interval_seconds), remaining)
            if on_wait is None:
                sleep_fn(wait_seconds)
                continue
            waited = 0.0
            while waited < wait_seconds:
                on_wait()
                chunk = min(
                    float(heartbeat_interval_seconds),
                    wait_seconds - waited,
                )
                sleep_fn(chunk)
                waited += chunk
        return "TIMEOUT"

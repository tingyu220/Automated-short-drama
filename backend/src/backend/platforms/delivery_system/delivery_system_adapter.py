"""投放系统真实 Adapter：Playwright Page Object 封装，dry_run 不操作页面."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.domain.ports.adapters import (
    DeliverySystemAdapter as DeliverySystemAdapterProtocol,
)
from backend.domain.ports.adapters import DramaAsset
from backend.platforms.delivery_system.page_objects.drama_asset_page import (
    DramaAssetPage,
)
from backend.platforms.delivery_system.page_objects.plan_submit_page import (
    PlanSubmitPage,
)
from backend.platforms.delivery_system.page_objects.promotion_config_page import (
    PromotionConfigPage,
)
from backend.platforms.delivery_system.page_objects.task_status_page import (
    TaskStatusPage,
)


logger = logging.getLogger(__name__)

_DEFAULT_SELECTORS_PATH = (
    Path(__file__).resolve().parents[5]
    / "configs"
    / "defaults"
    / "delivery_system_selectors.json"
)


def _load_default_selectors() -> dict[str, str]:
    """加载 configs/defaults/delivery_system_selectors.json."""
    with _DEFAULT_SELECTORS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


class DeliverySystemAdapter(DeliverySystemAdapterProtocol):
    """Playwright 版投放系统 Adapter；dry_run=True 只记录调用，不操作 page."""

    def __init__(
        self,
        selectors: dict[str, str] | None = None,
        page: Any = None,
        dry_run: bool = True,
    ) -> None:
        self._selectors = selectors or _load_default_selectors()
        self._page = page
        self._dry_run = dry_run
        self._recorded_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    @property
    def recorded_calls(self) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        """dry_run 模式下记录但未执行的调用（仅供测试/日志观察）。"""
        return list(self._recorded_calls)

    def find_or_create_drama_asset(self, drama_name: str, link: str) -> DramaAsset:
        """识别或创建剧目资源，幂等复用."""
        self._record("find_or_create_drama_asset", drama_name, link)
        if self._dry_run:
            return DramaAsset(delivery_drama_id="", drama_name=drama_name, link=link)
        return DramaAssetPage(self._page, self._selectors).find_or_create(
            drama_name, link
        )

    def ensure_promotion_config(self, asset_id: str, link_type: str, link: str) -> str:
        """创建缺失的推广内容配置并返回配置标识."""
        self._record("ensure_promotion_config", asset_id, link_type, link)
        if self._dry_run:
            return f"cfg-{asset_id}-{link_type}"
        config_name = f"{link_type}-{asset_id}"
        return PromotionConfigPage(self._page, self._selectors).create_missing(
            config_name, link
        )

    def submit_plan(self, plan_spec: Any) -> str:
        """提交标准投放计划并返回外部任务 ID."""
        self._record("submit_plan", plan_spec)
        if self._dry_run:
            return "dry-run-task"
        return PlanSubmitPage(self._page, self._selectors).submit(plan_spec)

    def poll_task_status(self, external_task_id: str) -> str:
        """轮询任务状态，返回标准状态字符串."""
        self._record("poll_task_status", external_task_id)
        if self._dry_run:
            return "PENDING"
        return TaskStatusPage(self._page, self._selectors).poll(external_task_id)

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self._recorded_calls.append((name, args, kwargs))
        logger.info("delivery system adapter 记录调用 dry_run=%s: %s", self._dry_run, name)

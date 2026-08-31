"""平台 Adapter Protocol 接口 —— Domain 层不依赖平台实现."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from backend.domain.tasks.drama_task import DramaTask
from backend.domain.rules.account_block import AccountRow
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch


@dataclass
class PromotionLink:
    """番茄推广链接纯数据."""

    drama_name: str
    link_type: str
    promotion_url: str
    source_platform: str = ""
    source_entry: str = ""
    acquisition_method: str = ""
    source_column: str = ""
    url_length: int = 0
    link_status: str = "PENDING"


@dataclass
class TemplateInfo:
    """番茄 IAP 模板信息."""

    template_id: str
    drama_name: str
    title: str
    price: float
    page_order: int


@dataclass
class DramaAsset:
    """投放系统剧目资源."""

    delivery_drama_id: str
    drama_name: str
    link: str
    album_id: str = ""


@runtime_checkable
class FeishuAdapter(Protocol):
    """飞书表读写协议."""

    def fetch_tasks(self, day: date) -> list[DramaTask]: ...
    def write_links(self, task_id: str, links: dict[str, str]) -> None: ...
    def write_completion(self, task_id: str) -> None: ...
    def read_status(self, task_id: str) -> str: ...
    def read_account_rows(self, kind: str) -> list[AccountRow]: ...
    def write_account_names(self, kind: str, assignments: dict[int, str]) -> None: ...
    def write_account_test_flags(self, kind: str, row_numbers: set[int]) -> None: ...
    def append_account_block(
        self,
        kind: str,
        expected_last_row: int,
        template_rows: list[AccountRow],
    ) -> list[AccountRow]: ...


@runtime_checkable
class TomatoAdapter(Protocol):
    """番茄链接提取协议."""

    def get_episode_count(
        self,
        drama_name: str,
        available_time: datetime,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> int: ...
    def extract_iaa_link(
        self,
        drama_name: str,
        available_time: datetime,
        episode_count: int,
        selected_episode: int,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> PromotionLink: ...
    def scan_iap_templates(
        self,
        drama_name: str,
        available_time: datetime,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> list[TemplateInfo]: ...
    def generate_iap_link(
        self,
        drama_name: str,
        available_time: datetime,
        template: TemplateInfo,
        confirmed_match: ConfirmedDramaMatch | None = None,
        target_price: float | None = None,
    ) -> PromotionLink: ...


@runtime_checkable
class DeliverySystemAdapter(Protocol):
    """投放系统资源与计划协议."""

    def find_or_create_drama_asset(self, drama_name: str, link: str) -> DramaAsset: ...
    def ensure_promotion_config(
        self,
        asset_id: str,
        link_type: str,
        link: str,
        drama_name: str,
        platform: str,
    ) -> str: ...
    def submit_plan(self, plan_spec: Any) -> str: ...
    def poll_task_status(self, external_task_id: str) -> str: ...
    def find_task_by_idempotency_key(self, task_name: str) -> str | None: ...


@runtime_checkable
class OceanEngineAdapter(Protocol):
    """巨量产品库协议."""

    def create_product(self, album_id: str, fields: dict[str, Any]) -> str: ...
    def verify_product(self, product_id: str) -> bool: ...


@runtime_checkable
class YouxuanAdapter(Protocol):
    """youxuan2 平台链接搭建协议（桩，后续扩展）。"""

    def extract_links(self, drama_name: str) -> list[PromotionLink]: ...

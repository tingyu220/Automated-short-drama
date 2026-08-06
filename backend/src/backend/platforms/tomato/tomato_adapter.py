"""番茄真实 Adapter：Playwright Page Object 封装，链接只从页面提取."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.platforms.tomato.page_objects.free_entry import FreeEntryPage
from backend.platforms.tomato.page_objects.paid_entry import PaidEntryPage


logger = logging.getLogger(__name__)

_DEFAULT_SELECTORS_PATH = (
    Path(__file__).resolve().parents[5] / "configs" / "defaults" / "tomato_selectors.json"
)


def _load_default_selectors() -> dict[str, str]:
    """加载 configs/defaults/tomato_selectors.json，选择器不写死在代码."""
    with _DEFAULT_SELECTORS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


class TomatoAdapter(TomatoAdapter):
    """Playwright 版番茄 Adapter；dry_run=True 只记录调用，不操作 page."""

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

    def extract_iaa_link(
        self,
        drama_name: str,
        episode_count: int,
        selected_episode: int,
    ) -> PromotionLink:
        self._record("extract_iaa_link", drama_name, episode_count, selected_episode)
        if self._dry_run:
            return self._empty_link(drama_name, "FREE")
        free_entry = FreeEntryPage(self._page, self._selectors)
        free_entry.search(drama_name)
        free_entry.open_detail()
        free_entry.generate_link(selected_episode)
        url = free_entry.read_link()
        return self._promotion_link(drama_name, "FREE", url)

    def scan_iap_templates(self, drama_name: str) -> list[TemplateInfo]:
        self._record("scan_iap_templates", drama_name)
        if self._dry_run:
            return []
        paid_entry = PaidEntryPage(self._page, self._selectors)
        return paid_entry.scan_templates(drama_name)

    def generate_iap_link(
        self,
        drama_name: str,
        template: TemplateInfo,
    ) -> PromotionLink:
        self._record("generate_iap_link", drama_name, template)
        if self._dry_run:
            return self._empty_link(drama_name, "PAID")
        paid_entry = PaidEntryPage(self._page, self._selectors)
        url = paid_entry.generate_link(template)
        return self._promotion_link(drama_name, "PAID", url)

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self._recorded_calls.append((name, args, kwargs))
        logger.info("tomato adapter 记录调用 dry_run=%s: %s", self._dry_run, name)

    @staticmethod
    def _promotion_link(drama_name: str, source_entry: str, url: str) -> PromotionLink:
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA" if source_entry == "FREE" else "IAP",
            promotion_url=url,
            source_platform="TOMATO",
            source_entry=source_entry,
            acquisition_method="PAGE_EXTRACTION",
            url_length=len(url),
            link_status="OK" if url else "PENDING",
        )

    @staticmethod
    def _empty_link(drama_name: str, source_entry: str) -> PromotionLink:
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA" if source_entry == "FREE" else "IAP",
            promotion_url="",
            source_platform="TOMATO",
            source_entry=source_entry,
            acquisition_method="PAGE_EXTRACTION",
            url_length=0,
            link_status="PENDING",
        )

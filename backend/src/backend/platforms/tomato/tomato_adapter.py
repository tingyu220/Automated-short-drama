"""番茄真实 Adapter：Playwright Page Object 封装，链接只从页面提取."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError
from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.platforms.tomato.page_objects.app_context import AppContextPage
from backend.platforms.tomato.page_objects.drama_selection import DramaSelectionPage
from backend.platforms.tomato.page_objects.free_entry import FreeEntryPage
from backend.platforms.tomato.page_objects.paid_entry import PaidEntryPage
from backend.platforms.tomato.page_objects.promotion_link_list import (
    PromotionLinkListPage,
)


logger = logging.getLogger(__name__)
_TOMATO_SESSION_EXPIRED = "TOMATO_SESSION_EXPIRED"
_IAP_SCAN_RETRIES = 2

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
        artifact_dir: Path | None = None,
    ) -> None:
        self._selectors = selectors or _load_default_selectors()
        self._page = page
        self._dry_run = dry_run
        self._artifact_dir = artifact_dir
        self._recorded_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self._iap_link_cache: dict[str, str] = {}
        self._claimed_iap_urls: set[str] = set()
        self._list_iap_cache: list[tuple[float, str, str]] = []
        self._list_iap_drama: str = ""
        self._current_context: str | None = None
        self.last_iap_search_diag: dict[str, Any] = {}

    @property
    def recorded_calls(self) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        """dry_run 模式下记录但未执行的调用（仅供测试/日志观察）。"""
        return list(self._recorded_calls)

    def get_episode_count(
        self,
        drama_name: str,
        available_time: datetime,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> int:
        self._record("get_episode_count", drama_name, available_time)
        if self._dry_run:
            return 1
        self._ensure_context("FREE")
        self._selection_page().select_and_verify(
            drama_name, available_time, confirmed_match
        )
        try:
            return FreeEntryPage(self._page, self._selectors).count_episodes()
        except Exception as exc:
            if not _should_reuse_existing(
                exc,
                "TOMATO_EPISODE_OPTIONS_EMPTY",
                "TOMATO_EPISODE_OPTION_MISSING",
            ):
                raise
            count = self._promotion_links().find_episode_count(drama_name)
            if count is None:
                raise
            return count

    def extract_iaa_link(
        self,
        drama_name: str,
        available_time: datetime,
        episode_count: int,
        selected_episode: int,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> PromotionLink:
        self._record(
            "extract_iaa_link",
            drama_name,
            available_time,
            episode_count,
            selected_episode,
        )
        if self._dry_run:
            return self._empty_link(drama_name, "FREE")
        # 先搜推广链列表，命中则直接复用，无需进入免费入口
        promotion_links = self._promotion_links()
        existing = promotion_links.find_iaa(drama_name, selected_episode)
        if existing is None:
            existing = promotion_links.find_existing(
                drama_name, f"{selected_episode}集"
            )
        if existing:
            return self._promotion_link(
                drama_name, "FREE", existing, "PROMOTION_LIST_VIEW"
            )
        # 推广链列表未命中，进入免费入口生成
        try:
            self._ensure_context("FREE")
        except Exception as exc:
            logger.warning(
                "FREE 入口上下文切换失败，推广链列表也未找到IAA链接 drama=%s episode=%d: %s",
                drama_name, selected_episode, exc,
            )
            raise
        self._selection_page().select_and_verify(
            drama_name, available_time, confirmed_match
        )
        free_entry = FreeEntryPage(self._page, self._selectors)
        try:
            free_entry.generate_link(selected_episode)
        except Exception as exc:
            if not _should_reuse_existing(
                exc,
                "TOMATO_EPISODE_OPTIONS_EMPTY",
                "TOMATO_EPISODE_OPTION_MISSING",
                "TOMATO_EPISODE_ALREADY_GENERATED",
            ):
                raise
            for retry in range(2):
                if retry > 0:
                    self._page.wait_for_timeout(2000)
                promotion_page = self._promotion_links()
                existing = promotion_page.find_iaa(
                    drama_name, selected_episode
                )
                if existing is None:
                    existing = promotion_page.find_existing(
                        drama_name, f"{selected_episode}集"
                    )
                if existing:
                    return self._promotion_link(
                        drama_name, "FREE", existing, "PROMOTION_LIST_VIEW"
                    )
            search_diag = promotion_page.debug_search_rows(drama_name)
            _enrich_error_details(
                exc,
                fallback_search_diag=search_diag,
                fallback_search_rows=search_diag.get("rows", []),
                fallback_search_count=search_diag.get(
                    "row_count_via_evaluate", 0
                ),
                fallback_search_count_alt=search_diag.get(
                    "row_count_via_count", 0
                ),
                fallback_search_url=search_diag.get("page_url", ""),
                fallback_search_title=search_diag.get("page_title", ""),
                fallback_search_tables=search_diag.get("table_count", 0),
                fallback_search_trs=search_diag.get("tr_count", 0),
                fallback_tr_details=search_diag.get("tr_details", []),
                fallback_view_buttons=search_diag.get("view_button_count", 0),
                fallback_view_btn_parents=search_diag.get(
                    "view_button_parent_classes", []
                ),
                fallback_body_text=search_diag.get("body_text_preview", ""),
                fallback_search_drama=drama_name,
                fallback_search_episode=selected_episode,
            )
            raise
        url = free_entry.read_link()
        return self._promotion_link(drama_name, "FREE", url)

    def scan_iap_templates(
        self,
        drama_name: str,
        available_time: datetime,
        confirmed_match: ConfirmedDramaMatch | None = None,
    ) -> list[TemplateInfo]:
        self._record("scan_iap_templates", drama_name, available_time)
        if self._dry_run:
            return []
        existing_templates = self._search_existing_iap(drama_name)
        if existing_templates:
            has_2_9 = any(
                self._price_in_target_range(t.price, 2.9)
                for t in existing_templates
            )
            has_9_9 = any(
                self._price_in_target_range(t.price, 9.9)
                for t in existing_templates
            )
            if has_2_9 and has_9_9:
                logger.info(
                    "IAP 链接已从推广链列表获取到2.9和9.9两档，跳过模板扫描 drama=%s",
                    drama_name,
                )
                return existing_templates
        try:
            self._ensure_context("PAID")
        except Exception as exc:
            logger.warning(
                "PAID 入口上下文切换失败，回退到推广链列表结果 drama=%s: %s",
                drama_name, exc,
            )
            return existing_templates
        self._selection_page().select_and_verify(
            drama_name, available_time, confirmed_match
        )
        paid_entry = PaidEntryPage(self._page, self._selectors)
        try:
            templates = paid_entry.scan_templates(drama_name)
        except Exception as exc:
            if not _should_reuse_existing(exc, "TOMATO_TEMPLATE_OPTIONS_EMPTY"):
                raise
            return existing_templates
        if templates and all(t.price == 0.0 for t in templates):
            logger.info(
                "IAP 模板扫描返回价格均为0，回退到推广链列表结果 drama=%s",
                drama_name,
            )
            return existing_templates
        if not templates:
            return existing_templates
        existing_prices = {t.price for t in existing_templates}
        for t in templates:
            if t.price not in existing_prices:
                existing_templates.append(t)
        return existing_templates

    def _search_existing_iap(self, drama_name: str) -> list[TemplateInfo]:
        """搜推广链列表已创建的 IAP 链接（过滤 IAA），同时填充两个缓存。

        先用"漫剧名称"搜索，若 IAP 不足再尝试无类型搜索，取结果更好的。
        """
        self._iap_link_cache.clear()
        self._claimed_iap_urls.clear()
        self._list_iap_drama = drama_name
        self._list_iap_cache = []

        diag: dict[str, Any] = {"search_attempts": []}

        # 获取搜索类型选项（诊断）
        try:
            list_page = self._promotion_links()
            # 先导航到列表页才能获取选项
            diag["search_type_options"] = list_page.get_search_type_options()
        except Exception as exc:
            diag["search_type_options_error"] = str(exc)[:100]

        best_iap: list[tuple[float, str, str]] = []
        best_all: list[tuple[float, str, str]] = []
        best_type: str = ""

        # 尝试不同搜索类型
        search_types: list[str | None] = ["漫剧名称", None]
        list_page = self._promotion_links()
        for stype in search_types:
            type_label = stype or "(默认/无类型)"
            try:
                all_links = list_page.list_iap(drama_name, search_type_name=stype)
                iap_links = [
                    (price, link, identity)
                    for price, link, identity in all_links
                    if price > 0.0
                ]
                diag["search_attempts"].append({
                    "type": type_label,
                    "total_rows": len(all_links),
                    "iap_count": len(iap_links),
                    "all_prices": [p for p, _, _ in all_links],
                    "all_identities": [i for _, _, i in all_links],
                })
                if len(iap_links) > len(best_iap):
                    best_iap = iap_links
                    best_all = all_links
                    best_type = type_label
            except Exception as exc:
                diag["search_attempts"].append({
                    "type": type_label,
                    "error": f"{type(exc).__name__}: {str(exc)[:100]}",
                })

        self._list_iap_cache = best_iap
        diag["best_search_type"] = best_type
        diag["total_rows"] = len(best_all)
        diag["iap_count"] = len(best_iap)
        diag["all_prices"] = [p for p, _, _ in best_all]
        diag["all_identities"] = [i for _, _, i in best_all]
        self.last_iap_search_diag = diag

        templates: list[TemplateInfo] = []
        for index, (price, link, identity) in enumerate(best_iap, start=1):
            cache_key = f"{identity or str(price)}#{index}"
            self._iap_link_cache[cache_key] = link
            templates.append(
                TemplateInfo(
                    template_id=identity or str(price),
                    drama_name=drama_name,
                    title=identity or str(price),
                    price=price,
                    page_order=index,
                )
            )
        logger.info(
            "推广链列表搜索完成 drama=%s best_type=%s total=%d iap=%d prices=%s",
            drama_name,
            best_type,
            len(best_all),
            len(best_iap),
            [p for p, _, _ in best_iap],
        )
        return templates

    def _find_in_iap_list_cache(
        self, drama_name: str, search_price: float, identity: str
    ) -> str | None:
        """从预加载的 IAP 列表中按价格范围或标识查找未占用的链接。"""
        if self._list_iap_drama != drama_name or not self._list_iap_cache:
            return None
        for price, link, link_identity in self._list_iap_cache:
            if link in self._claimed_iap_urls:
                continue
            if search_price > 0 and self._price_in_target_range(price, search_price):
                return link
        for price, link, link_identity in self._list_iap_cache:
            if link in self._claimed_iap_urls:
                continue
            if identity and link_identity and (
                identity in link_identity or link_identity in identity
            ):
                return link
        return None

    @staticmethod
    def _price_in_target_range(price: float, target: float) -> bool:
        """检查价格是否落在目标档位范围内（2.9: 2.0-5.0, 9.9: 8.0-15.0）。"""
        if abs(target - 2.9) < 0.01:
            return 2.0 <= price <= 5.0
        if abs(target - 9.9) < 0.01:
            return 8.0 <= price <= 15.0
        return abs(price - target) < 0.01

    def generate_iap_link(
        self,
        drama_name: str,
        available_time: datetime,
        template: TemplateInfo,
        confirmed_match: ConfirmedDramaMatch | None = None,
        target_price: float | None = None,
    ) -> PromotionLink:
        self._record("generate_iap_link", drama_name, available_time, template)
        if self._dry_run:
            return self._empty_link(drama_name, "PAID")
        template_identity = template.title or template.template_id
        cache_key = f"{template_identity}#{template.page_order}"
        cached_url = self._iap_link_cache.pop(cache_key, None)
        if cached_url and cached_url in self._claimed_iap_urls:
            for alt_key, alt_url in list(self._iap_link_cache.items()):
                if alt_url not in self._claimed_iap_urls:
                    self._iap_link_cache.pop(alt_key)
                    cached_url = alt_url
                    logger.debug(
                        "IAP cache primary URL已占用，使用备选 key=%s", alt_key
                    )
                    break
            else:
                logger.debug("IAP cache命中但URL已占用，跳过缓存")
                cached_url = None
        logger.debug(
            "generate_iap_link drama=%s identity=%s price=%s page_order=%s "
            "target_price=%s cache_hit=%s",
            drama_name, template_identity, template.price,
            template.page_order, target_price, cached_url is not None,
        )
        if cached_url:
            self._claimed_iap_urls.add(cached_url)
            return self._promotion_link(drama_name, "PAID", cached_url)
        search_price = target_price if target_price is not None else template.price
        if search_price == 0.0 and template.page_order > 0:
            search_price = 2.9 if template.page_order == 1 else 9.9
        list_url = self._find_in_iap_list_cache(drama_name, search_price, template_identity)
        if list_url:
            logger.debug(
                "IAP list_cache命中 price=%s identity=%s",
                search_price, template_identity,
            )
            self._claimed_iap_urls.add(list_url)
            return self._promotion_link(
                drama_name, "PAID", list_url, "PROMOTION_LIST_VIEW"
            )
        self._ensure_context("PAID")
        self._selection_page().select_and_verify(
            drama_name, available_time, confirmed_match
        )
        promotion_links = self._promotion_links()
        existing = None
        if search_price > 0:
            existing = promotion_links.find_iap(drama_name, search_price)
            logger.debug(
                "find_iap price=%s → %s", search_price,
                "found" if existing else "None",
            )
        if existing is None:
            existing = promotion_links.find_existing(drama_name, template_identity)
            logger.debug(
                "find_existing identity=%s → %s", template_identity,
                "found" if existing else "None",
            )
        if existing and existing not in self._claimed_iap_urls:
            self._claimed_iap_urls.add(existing)
            return self._promotion_link(
                drama_name, "PAID", existing, "PROMOTION_LIST_VIEW"
            )
        elif existing:
            logger.debug("existing URL已占用，生成新链接")
        if template.page_order == 0:
            logger.debug("合成模板，无链接可生成")
            return self._empty_link(drama_name, "PAID")
        self._selection_page().select_and_verify(
            drama_name, available_time, confirmed_match
        )
        paid_entry = PaidEntryPage(self._page, self._selectors)
        try:
            url = paid_entry.generate_link(template)
        except Exception as exc:
            if not _should_reuse_existing(
                exc,
                "TOMATO_TEMPLATE_OPTIONS_EMPTY",
                "TOMATO_TEMPLATE_OPTION_MISSING",
                "TOMATO_TEMPLATE_ALREADY_GENERATED",
            ):
                raise
            for retry in range(2):
                if retry > 0:
                    self._page.wait_for_timeout(2000)
                promotion_page = self._promotion_links()
                retry_price = target_price if target_price is not None else template.price
                existing = promotion_page.find_iap(drama_name, retry_price)
                if existing and existing not in self._claimed_iap_urls:
                    self._claimed_iap_urls.add(existing)
                    return self._promotion_link(
                        drama_name, "PAID", existing, "PROMOTION_LIST_VIEW"
                    )
                if existing is None:
                    for _, link, _ in promotion_page.list_iap(drama_name):
                        if link and link not in self._claimed_iap_urls:
                            self._claimed_iap_urls.add(link)
                            return self._promotion_link(
                                drama_name, "PAID", link, "PROMOTION_LIST_VIEW"
                            )
            raise
        self._claimed_iap_urls.add(url)
        return self._promotion_link(drama_name, "PAID", url)

    def _selection_page(self) -> DramaSelectionPage:
        return DramaSelectionPage(
            self._page,
            self._selectors,
            self._artifact_dir,
        )

    def _ensure_context(self, source_entry: str) -> None:
        if self._current_context == source_entry:
            return
        self._page.goto(
            self._selectors.get("context_url", self._selectors["login_url"]),
            wait_until="domcontentloaded",
            timeout=60000,
        )
        self._check_session()
        AppContextPage(self._page, self._selectors).ensure(source_entry)
        self._current_context = source_entry

    def _check_session(self) -> None:
        """检测番茄平台会话失效（重定向到登录页或出现登录表单）。"""
        current_url = self._page.url
        if any(kw in current_url.lower() for kw in ("login", "passport", "auth")):
            raise ExternalAdapterError(
                "番茄平台登录态已失效，请重新登录",
                code=_TOMATO_SESSION_EXPIRED,
                details={"current_url": current_url},
            )
        try:
            has_login_form = self._page.locator(
                "input[type='password']"
            ).first.is_visible(timeout=1000)
        except Exception:
            has_login_form = False
        if has_login_form:
            raise ExternalAdapterError(
                "番茄平台登录态已失效（检测到登录表单），请重新登录",
                code=_TOMATO_SESSION_EXPIRED,
                details={"current_url": current_url},
            )

    def _promotion_links(self) -> PromotionLinkListPage:
        return PromotionLinkListPage(self._page, self._selectors)

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self._recorded_calls.append((name, args, kwargs))
        logger.info("tomato adapter 记录调用 dry_run=%s: %s", self._dry_run, name)

    @staticmethod
    def _promotion_link(
        drama_name: str,
        source_entry: str,
        url: str,
        acquisition_method: str = "PAGE_EXTRACTION",
    ) -> PromotionLink:
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA" if source_entry == "FREE" else "IAP",
            promotion_url=url,
            source_platform="TOMATO",
            source_entry=source_entry,
            acquisition_method=acquisition_method,
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


def _should_reuse_existing(
    error: Exception, expected_code: str, *additional_codes: str
) -> bool:
    code = getattr(error, "code", "")
    if code not in {expected_code, *additional_codes}:
        return False
    if code in (
        "TOMATO_EPISODE_OPTION_MISSING",
        "TOMATO_EPISODE_ALREADY_GENERATED",
        "TOMATO_TEMPLATE_OPTION_MISSING",
        "TOMATO_TEMPLATE_ALREADY_GENERATED",
    ):
        return True
    return getattr(error, "details", {}).get("reason") in {
        "ALL_OPTIONS_ALREADY_CREATED",
        "OPTIONS_NOT_LOADED",
    }


def _enrich_error_details(error: Exception, **kwargs: object) -> None:
    """向异常的 details 字典追加诊断信息。"""
    details = getattr(error, "details", None)
    if details is None:
        details = {}
        try:
            setattr(error, "details", details)
        except AttributeError:
            pass
    if isinstance(details, dict):
        details.update(kwargs)

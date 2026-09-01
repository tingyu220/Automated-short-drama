"""番茄 IAA 选集与 IAP 模板扫描模拟服务."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.rules.template_price_rule import TemplatePriceRule

logger = logging.getLogger(__name__)

DEFAULT_EPISODE_THRESHOLD = 50
_IAP_TARGET_2_9 = 2.9
_IAP_TARGET_9_9 = 9.9
_SCAN_IAA_DEFAULT_EPISODE_COUNT = 1
_IAP_SCAN_RETRIES = 2


@dataclass
class IapScanResult:
    """IAP 模板扫描结果：业务结论、各档链接与命中模板。"""

    business_result: str
    iaa_link: PromotionLink
    iap_2_9_link: PromotionLink | None = None
    iap_9_9_link: PromotionLink | None = None
    matched_templates: list[TemplateInfo] = field(default_factory=list)
    iap_failures: list[dict[str, str]] = field(default_factory=list)
    diag: dict[str, Any] = field(default_factory=dict)


def extract_iaa(
    drama_name: str,
    available_time: datetime,
    episode_count: int,
    tomato: TomatoAdapter,
    episode_threshold: int = DEFAULT_EPISODE_THRESHOLD,
    confirmed_match: ConfirmedDramaMatch | None = None,
) -> PromotionLink:
    """按集数阈值选择免费入口集数并提取 IAA 链接."""
    selected_episode = 2 if episode_count > episode_threshold else 1
    if confirmed_match is None:
        return tomato.extract_iaa_link(
            drama_name, available_time, episode_count, selected_episode
        )
    return tomato.extract_iaa_link(
        drama_name, available_time, episode_count, selected_episode, confirmed_match
    )


def scan_iap(
    drama_name: str,
    available_time: datetime,
    tomato: TomatoAdapter,
    price_rules: list[TemplatePriceRule],
    *,
    episode_count: int = _SCAN_IAA_DEFAULT_EPISODE_COUNT,
    confirmed_match: ConfirmedDramaMatch | None = None,
) -> IapScanResult:
    """先提取必需的 IAA，再尽力获取可选 IAP。"""
    logger.info("scan_iap drama=%s episode=%s", drama_name, episode_count)
    iaa_link = extract_iaa(
        drama_name,
        available_time,
        episode_count,
        tomato,
        confirmed_match=confirmed_match,
    )
    try:
        templates = _scan_templates_with_retry(
            tomato, drama_name, available_time, confirmed_match
        )
        iap_diag = dict(getattr(tomato, "last_iap_search_diag", {}))
        iap_diag["template_count"] = len(templates)
        iap_diag["template_prices"] = [t.price for t in templates]
        logger.info(
            "IAP 模板扫描完成 drama=%s templates=%d prices=%s",
            drama_name,
            len(templates),
            [t.price for t in templates],
        )
    except Exception as exc:
        iap_diag = dict(getattr(tomato, "last_iap_search_diag", {}))
        iap_diag["scan_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        logger.warning(
            "IAP 模板扫描失败 drama=%s error=%s: %s",
            drama_name,
            type(exc).__name__,
            exc,
        )
        result = IapScanResult(
            business_result="IAP_FAILED",
            iaa_link=iaa_link,
            iap_failures=[_iap_failure("IAP", exc)],
            diag=iap_diag,
        )
        return result
    enabled_rules = [rule for rule in price_rules if rule.enabled]
    logger.info(
        "IAP 价格规则 drama=%s enabled_rules=%d targets=%s",
        drama_name,
        len(enabled_rules),
        [r.target_price for r in enabled_rules],
    )

    print(f"[DEBUG scan_iap] drama={drama_name} all_templates={len(templates)} template_prices={[t.price for t in templates]}", flush=True)
    print(f"[DEBUG scan_iap] enabled_rules={len(enabled_rules)} rule_targets={[r.target_price for r in enabled_rules]} rule_ranges=[(r.min_price, r.max_price) for r in enabled_rules]", flush=True)
    in_range_2_9 = _in_range_templates(templates, enabled_rules, _IAP_TARGET_2_9)
    in_range_9_9 = _in_range_templates(templates, enabled_rules, _IAP_TARGET_9_9)
    best_2_9 = _pick_best(in_range_2_9, _IAP_TARGET_2_9)
    best_9_9 = _pick_best(in_range_9_9, _IAP_TARGET_9_9)
    print(f"[DEBUG scan_iap] in_range_2_9={len(in_range_2_9)} in_range_9_9={len(in_range_9_9)} best_2_9={best_2_9.price if best_2_9 else None} best_9_9={best_9_9.price if best_9_9 else None}", flush=True)
    logger.info(
        "IAP 模板匹配 drama=%s in_range_2_9=%d in_range_9_9=%d best_2_9=%s best_9_9=%s",
        drama_name,
        len(in_range_2_9),
        len(in_range_9_9),
        best_2_9.price if best_2_9 else "None",
        best_9_9.price if best_9_9 else "None",
    )
    link_2_9, failure_2_9 = _try_generate_iap_link(
        tomato, drama_name, available_time, best_2_9, "2.9", confirmed_match,
        target_price=_IAP_TARGET_2_9,
    )
    link_9_9, failure_9_9 = _try_generate_iap_link(
        tomato, drama_name, available_time, best_9_9, "9.9", confirmed_match,
        target_price=_IAP_TARGET_9_9,
    )
    failures = [failure for failure in (failure_2_9, failure_9_9) if failure]
    matched_templates = [
        template for template in (best_2_9, best_9_9) if template is not None
    ]
    return IapScanResult(
        business_result=_iap_business_result(
            bool(link_2_9 and link_2_9.promotion_url),
            bool(link_9_9 and link_9_9.promotion_url),
            bool(failures),
        ),
        iaa_link=iaa_link,
        iap_2_9_link=link_2_9,
        iap_9_9_link=link_9_9,
        matched_templates=matched_templates,
        iap_failures=failures,
        diag=iap_diag,
    )


def _try_generate_iap_link(
    tomato: TomatoAdapter,
    drama_name: str,
    available_time: datetime,
    template: TemplateInfo | None,
    link_type: str,
    confirmed_match: ConfirmedDramaMatch | None,
    *,
    target_price: float | None = None,
) -> tuple[PromotionLink | None, dict[str, str] | None]:
    if template is None:
        return None, None
    try:
        return (
            _generate_iap_link(
                tomato, drama_name, available_time, template, confirmed_match,
                target_price=target_price,
            ),
            None,
        )
    except Exception as exc:
        return None, _iap_failure(link_type, exc)


def _iap_failure(link_type: str, error: Exception) -> dict[str, str]:
    code = getattr(error, "code", type(error).__name__)
    return {
        "link_type": link_type,
        "code": str(code),
        "message": str(error),
    }


def _scan_templates_with_retry(
    tomato: TomatoAdapter,
    drama_name: str,
    available_time: datetime,
    confirmed_match: ConfirmedDramaMatch | None,
) -> list[TemplateInfo]:
    """带重试的模板扫描，会话失效类错误不重试直接抛出。"""
    last_exc: Exception | None = None
    for attempt in range(_IAP_SCAN_RETRIES + 1):
        try:
            if confirmed_match is None:
                return tomato.scan_iap_templates(drama_name, available_time)
            return tomato.scan_iap_templates(
                drama_name, available_time, confirmed_match
            )
        except Exception as exc:
            code = getattr(exc, "code", "")
            if code in ("TOMATO_SESSION_EXPIRED", "SESSION_EXPIRED"):
                raise
            last_exc = exc
            if attempt < _IAP_SCAN_RETRIES:
                logger.info(
                    "IAP 模板扫描第 %d 次失败，准备重试 drama=%s error=%s",
                    attempt + 1,
                    drama_name,
                    code or type(exc).__name__,
                )
    if last_exc:
        raise last_exc
    return []


def _generate_iap_link(
    tomato: TomatoAdapter,
    drama_name: str,
    available_time: datetime,
    template: TemplateInfo,
    confirmed_match: ConfirmedDramaMatch | None,
    *,
    target_price: float | None = None,
) -> PromotionLink:
    if confirmed_match is None:
        return tomato.generate_iap_link(
            drama_name, available_time, template, target_price=target_price,
        )
    return tomato.generate_iap_link(
        drama_name, available_time, template, confirmed_match,
        target_price=target_price,
    )


def _in_range_templates(
    templates: list[TemplateInfo],
    rules: list[TemplatePriceRule],
    target_price: float,
) -> list[TemplateInfo]:
    """按目标档位区间过滤模板，区间外模板直接忽略."""
    bucket_rules = [
        rule
        for rule in rules
        if math.isclose(rule.target_price, target_price, abs_tol=1e-9)
    ]
    if not bucket_rules:
        return []
    return [
        template
        for template in templates
        if any(
            rule.min_price <= template.price <= rule.max_price
            for rule in bucket_rules
        )
    ]


def _pick_best(
    templates: list[TemplateInfo],
    target_price: float,
) -> TemplateInfo | None:
    """同距离优先高价，再按 page_order 升序选择最佳模板."""
    if not templates:
        return None

    def sort_key(template: TemplateInfo) -> tuple[float, float, int]:
        return (
            abs(template.price - target_price),
            -template.price,
            template.page_order,
        )

    return min(templates, key=sort_key)


def _business_result(
    has_2_9: bool,
    has_9_9: bool,
) -> str:
    """输出 2.9/9.9 档位的可用性结论."""
    if has_2_9 and has_9_9:
        return "BOTH_AVAILABLE"
    if has_2_9:
        return "ONLY_2_9_AVAILABLE"
    if has_9_9:
        return "ONLY_9_9_AVAILABLE"
    return "NO_MATCHING_TEMPLATE"


def _iap_business_result(
    has_2_9: bool,
    has_9_9: bool,
    has_failures: bool,
) -> str:
    if has_failures:
        return "IAP_PARTIAL_FAILURE" if has_2_9 or has_9_9 else "IAP_FAILED"
    return _business_result(has_2_9, has_9_9)

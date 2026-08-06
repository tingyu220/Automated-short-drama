"""番茄 IAA 选集与 IAP 模板扫描模拟服务."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.domain.rules.template_price_rule import TemplatePriceRule

DEFAULT_EPISODE_THRESHOLD = 50
_IAP_TARGET_2_9 = 2.9
_IAP_TARGET_9_9 = 9.9
_SCAN_IAA_DEFAULT_EPISODE_COUNT = 1


@dataclass
class IapScanResult:
    """IAP 模板扫描结果：业务结论、各档链接与命中模板。"""

    business_result: str
    iaa_link: PromotionLink
    iap_2_9_link: PromotionLink | None = None
    iap_9_9_link: PromotionLink | None = None
    matched_templates: list[TemplateInfo] = field(default_factory=list)


def extract_iaa(
    drama_name: str,
    episode_count: int,
    tomato: TomatoAdapter,
    episode_threshold: int = DEFAULT_EPISODE_THRESHOLD,
) -> PromotionLink:
    """按集数阈值选择免费入口集数并提取 IAA 链接."""
    selected_episode = 2 if episode_count > episode_threshold else 1
    return tomato.extract_iaa_link(drama_name, episode_count, selected_episode)


def scan_iap(
    drama_name: str,
    tomato: TomatoAdapter,
    price_rules: list[TemplatePriceRule],
) -> IapScanResult:
    """扫描全部 IAP 模板，按价格区间归类并生成 2.9/9.9 档链接."""
    templates = tomato.scan_iap_templates(drama_name)
    enabled_rules = [rule for rule in price_rules if rule.enabled]

    best_2_9 = _pick_best(
        _in_range_templates(templates, enabled_rules, _IAP_TARGET_2_9),
        _IAP_TARGET_2_9,
    )
    best_9_9 = _pick_best(
        _in_range_templates(templates, enabled_rules, _IAP_TARGET_9_9),
        _IAP_TARGET_9_9,
    )

    link_2_9 = (
        tomato.generate_iap_link(drama_name, best_2_9) if best_2_9 else None
    )
    link_9_9 = (
        tomato.generate_iap_link(drama_name, best_9_9) if best_9_9 else None
    )
    matched_templates = [
        template for template in (best_2_9, best_9_9) if template is not None
    ]
    return IapScanResult(
        business_result=_business_result(link_2_9 is not None, link_9_9 is not None),
        # scan_iap 无集数入参，IAA 链接按默认第 1 集生成。
        iaa_link=extract_iaa(
            drama_name,
            _SCAN_IAA_DEFAULT_EPISODE_COUNT,
            tomato,
        ),
        iap_2_9_link=link_2_9,
        iap_9_9_link=link_9_9,
        matched_templates=matched_templates,
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

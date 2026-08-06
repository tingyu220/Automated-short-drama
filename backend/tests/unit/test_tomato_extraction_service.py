"""番茄链接/模板提取服务单元测试：fake tomato + price rules."""
from __future__ import annotations

from backend.application.services.tomato_extraction_service import (
    IapScanResult,
    extract_iaa,
    scan_iap,
)
from backend.domain.ports.adapters import PromotionLink, TemplateInfo
from backend.domain.rules.template_price_rule import TemplatePriceRule


def _rule(
    target: float,
    min_price: float,
    max_price: float,
    key: str = "",
) -> TemplatePriceRule:
    """构造价格规则."""
    return TemplatePriceRule(
        key=key,
        target_price=target,
        min_price=min_price,
        max_price=max_price,
    )


def _template(
    template_id: str,
    price: float,
    page_order: int = 1,
) -> TemplateInfo:
    """构造模板信息."""
    return TemplateInfo(
        template_id=template_id,
        drama_name="剧A",
        title=f"模板 {template_id}",
        price=price,
        page_order=page_order,
    )


class FakeTomatoAdapter:
    """可注入模板的番茄 Adapter fake."""

    def __init__(self, templates: list[TemplateInfo] | None = None) -> None:
        self.templates = templates or []

    def extract_iaa_link(
        self,
        drama_name: str,
        episode_count: int,
        selected_episode: int,
    ) -> PromotionLink:
        del episode_count
        url = f"mock://iaa/{drama_name}?ep={selected_episode}"
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA",
            promotion_url=url,
            source_platform="TOMATO",
            source_entry="FREE",
            acquisition_method="FAKE",
            source_column="J",
            url_length=len(url),
            link_status="OK",
        )

    def scan_iap_templates(self, drama_name: str) -> list[TemplateInfo]:
        del drama_name
        return list(self.templates)

    def generate_iap_link(
        self,
        drama_name: str,
        template: TemplateInfo,
    ) -> PromotionLink:
        url = f"mock://iap/{drama_name}?tpl={template.template_id}"
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAP",
            promotion_url=url,
            source_platform="TOMATO",
            source_entry="PAID",
            acquisition_method="FAKE",
            source_column="K",
            url_length=len(url),
            link_status="OK",
        )


def _both_rules() -> list[TemplatePriceRule]:
    """2.9 与 9.9 各一条价格规则."""
    return [
        _rule(2.9, 2.6, 5.0, key="iap_2_9"),
        _rule(9.9, 8.8, 13.8, key="iap_9_9"),
    ]


class TestExtractIaa:
    """extract_iaa 选集边界测试."""

    def test_50_episodes_selects_episode_1(self) -> None:
        link = extract_iaa("剧A", 50, FakeTomatoAdapter())

        assert link.link_type == "IAA"
        assert link.promotion_url.endswith("ep=1")

    def test_51_episodes_selects_episode_2(self) -> None:
        link = extract_iaa("剧A", 51, FakeTomatoAdapter())

        assert link.link_type == "IAA"
        assert link.promotion_url.endswith("ep=2")

    def test_custom_threshold(self) -> None:
        link = extract_iaa("剧A", 50, FakeTomatoAdapter(), episode_threshold=49)

        assert link.promotion_url.endswith("ep=2")


class TestScanIap:
    """scan_iap 分类、排序与业务结果测试."""

    def test_same_distance_higher_price_wins(self) -> None:
        tomato = FakeTomatoAdapter(
            [
                _template("tpl-9-8", 9.8, page_order=1),
                _template("tpl-10-0", 10.0, page_order=2),
                _template("tpl-10-5", 10.5, page_order=3),
            ]
        )

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.business_result == "ONLY_9_9_AVAILABLE"
        assert result.iap_9_9_link is not None
        assert result.iap_9_9_link.promotion_url.endswith("tpl-10-0")
        assert [template.template_id for template in result.matched_templates] == [
            "tpl-10-0"
        ]

    def test_only_2_9_available(self) -> None:
        tomato = FakeTomatoAdapter([_template("tpl-2-9", 2.9)])

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.business_result == "ONLY_2_9_AVAILABLE"
        assert result.iap_2_9_link is not None
        assert result.iap_2_9_link.promotion_url.endswith("tpl-2-9")
        assert result.iap_9_9_link is None
        assert [template.template_id for template in result.matched_templates] == [
            "tpl-2-9"
        ]

    def test_only_9_9_available(self) -> None:
        tomato = FakeTomatoAdapter([_template("tpl-9-9", 9.9)])

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.business_result == "ONLY_9_9_AVAILABLE"
        assert result.iap_2_9_link is None
        assert result.iap_9_9_link is not None
        assert result.iap_9_9_link.promotion_url.endswith("tpl-9-9")
        assert [template.template_id for template in result.matched_templates] == [
            "tpl-9-9"
        ]

    def test_no_matching_template(self) -> None:
        tomato = FakeTomatoAdapter([_template("tpl-out", 25.0)])

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.business_result == "NO_MATCHING_TEMPLATE"
        assert result.iap_2_9_link is None
        assert result.iap_9_9_link is None
        assert result.matched_templates == []

    def test_both_available(self) -> None:
        tomato = FakeTomatoAdapter(
            [_template("tpl-2-9", 2.9), _template("tpl-9-9", 9.9)]
        )

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.business_result == "BOTH_AVAILABLE"
        assert result.iap_2_9_link is not None
        assert result.iap_9_9_link is not None
        assert [template.template_id for template in result.matched_templates] == [
            "tpl-2-9",
            "tpl-9-9",
        ]

    def test_out_of_range_templates_ignored(self) -> None:
        tomato = FakeTomatoAdapter(
            [
                _template("tpl-out", 25.0),
                _template("tpl-2-9", 2.9),
                _template("tpl-9-9", 9.9),
            ]
        )

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.business_result == "BOTH_AVAILABLE"
        assert [template.template_id for template in result.matched_templates] == [
            "tpl-2-9",
            "tpl-9-9",
        ]

    def test_same_price_lower_page_order_wins(self) -> None:
        tomato = FakeTomatoAdapter(
            [
                _template("tpl-late", 9.9, page_order=2),
                _template("tpl-early", 9.9, page_order=1),
            ]
        )

        result = scan_iap("剧A", tomato, _both_rules())

        assert result.iap_9_9_link is not None
        assert result.iap_9_9_link.promotion_url.endswith("tpl-early")

    def test_disabled_rule_ignored(self) -> None:
        tomato = FakeTomatoAdapter([_template("tpl-2-9", 2.9)])
        disabled = _rule(2.9, 2.6, 5.0, key="disabled")
        disabled.enabled = False

        result = scan_iap("剧A", tomato, [disabled])

        assert result.business_result == "NO_MATCHING_TEMPLATE"
        assert result.iap_2_9_link is None

    def test_result_contains_iaa_link(self) -> None:
        tomato = FakeTomatoAdapter([_template("tpl-9-9", 9.9)])

        result = scan_iap("剧A", tomato, _both_rules())

        assert isinstance(result, IapScanResult)
        assert result.iaa_link.link_type == "IAA"
        assert result.iaa_link.source_platform == "TOMATO"

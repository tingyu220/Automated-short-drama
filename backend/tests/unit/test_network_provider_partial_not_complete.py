"""验证 NetworkProvider 不会因只找到 IAA 就返回 COMPLETE。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.acquisition.acquisition_result import AcquisitionStatus
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.network.network_listener import NetworkCapture
from backend.platforms.tomato.network.response_parser import (
    ParsedPromotion,
    TomatoResponseParser,
)
from backend.platforms.tomato.providers.network_provider import NetworkProvider


class _FakeListener:
    """模拟 NetworkListener，返回预设 captures。"""

    def __init__(self, captures=None, grouped=None):
        self._captures = captures or []
        self._grouped = grouped or {}

    @property
    def captures(self):
        return list(self._captures)

    @property
    def grouped_captures(self):
        return dict(self._grouped)


class _FakeParser:
    """模拟 ResponseParser，返回预设解析结果。"""

    def __init__(self, parsed_items):
        self._parsed = parsed_items

    def parse_promotion_list(self, response):
        return list(self._parsed)

    def parse_promotion_detail(self, response):
        return None


def _task():
    return DramaTask(
        id="task-1",
        sheet_row=1,
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links={},
    )


def _price_rules():
    from backend.domain.rules.template_price_rule import TemplatePriceRule

    return [
        TemplatePriceRule(target_price=2.9, min_price=2.0, max_price=5.0, key="iap_2_9"),
        TemplatePriceRule(target_price=9.9, min_price=7.0, max_price=15.0, key="iap_9_9"),
    ]


def _make_parsed(link_type, promotion_id="p1", drama_name="剧A", url="aweme://playlet?x=1"):
    from backend.domain.assets.promotion_asset import PromotionAsset
    return PromotionAsset(
        id="a1",
        task_id="task-1",
        source_platform="TOMATO",
        drama_name=drama_name,
        link_type=link_type,
        promotion_url=url,
        promotion_id=promotion_id,
        external_drama_id="drama-1",
    )


class TestNetworkProviderPartialNotComplete:
    """Phase 2: NetworkProvider 不应因只找到 IAA 就返回 COMPLETE。"""

    def test_only_iaa_found_returns_partial(self):
        """只有 IAA 找到，2.9/9.9 缺失 → PARTIAL，不是 COMPLETE。"""
        from backend.domain.assets.promotion_asset import (
            AcquisitionMethod,
            AssetStatus,
            CreationStatus,
            PromotionAsset,
        )

        iaa_asset = PromotionAsset(
            id="a1",
            task_id="task-1",
            source_platform="TOMATO",
            drama_name="剧A",
            link_type="IAA",
            promotion_url="aweme://playlet?x=1",
            promotion_id="p1",
            external_drama_id="drama-1",
            acquisition_method=AcquisitionMethod.NETWORK,
            acquisition_status=AssetStatus.DISCOVERED,
            created_or_existing=CreationStatus.EXISTING,
        )

        listener = _FakeListener(
            grouped={"PROMOTION_LIST": [NetworkCapture(url="x", method="GET", status=200, endpoint_type="PROMOTION_LIST", response_body={})]}
        )

        class StubParser:
            def parse_promotion_list(self, response):
                from backend.platforms.tomato.network.response_parser import ParsedPromotion
                return [
                    ParsedPromotion(
                        promotion_id="p1",
                        drama_name="剧A",
                        link_type="IAA",
                        promotion_url="aweme://playlet?x=1",
                        external_drama_id="drama-1",
                    ),
                ]

            def parse_promotion_detail(self, response):
                return None

        provider = NetworkProvider(listener, _price_rules(), parser=StubParser())
        result = provider.acquire(_task())

        assert result.status != AcquisitionStatus.COMPLETE
        assert result.status == AcquisitionStatus.PARTIAL
        assert "IAA" in [a.link_type for a in result.selected]
        assert "2.9" in result.missing
        assert "9.9" in result.missing

    def test_all_found_returns_complete(self):
        """IAA + 2.9 + 9.9 全部找到 → COMPLETE。"""
        from backend.platforms.tomato.network.response_parser import ParsedPromotion

        parsed_items = [
            ParsedPromotion(promotion_id="p1", drama_name="剧A", link_type="IAA", promotion_url="aweme://playlet?x=1", external_drama_id="drama-1"),
            ParsedPromotion(promotion_id="p2", drama_name="剧A", link_type="2.9", promotion_url="aweme://playlet?x=2", external_drama_id="drama-1", price=2.9),
            ParsedPromotion(promotion_id="p3", drama_name="剧A", link_type="9.9", promotion_url="aweme://playlet?x=3", external_drama_id="drama-1", price=9.9),
        ]

        listener = _FakeListener(
            grouped={"PROMOTION_LIST": [NetworkCapture(url="x", method="GET", status=200, endpoint_type="PROMOTION_LIST", response_body={})]}
        )

        class StubParser:
            def parse_promotion_list(self, response):
                return list(parsed_items)

            def parse_promotion_detail(self, response):
                return None

        provider = NetworkProvider(listener, _price_rules(), parser=StubParser())
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE
        assert len(result.selected) == 3
        assert set(result.missing.keys()) == set()

    def test_nothing_found_returns_not_found(self):
        """全部缺失 → NOT_FOUND。"""
        listener = _FakeListener(
            grouped={"PROMOTION_LIST": [NetworkCapture(url="x", method="GET", status=200, endpoint_type="PROMOTION_LIST", response_body={})]}
        )

        class StubParser:
            def parse_promotion_list(self, response):
                return []

            def parse_promotion_detail(self, response):
                return None

        provider = NetworkProvider(listener, _price_rules(), parser=StubParser())
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.NOT_FOUND
        assert len(result.selected) == 0

    def test_expected_types_always_full(self):
        """expected_types 永远是 ['IAA', '2.9', '9.9']，不因匹配结果变化。"""
        from backend.platforms.tomato.network.response_parser import ParsedPromotion

        parsed_items = [
            ParsedPromotion(promotion_id="p1", drama_name="剧A", link_type="IAA", promotion_url="aweme://playlet?x=1", external_drama_id="drama-1"),
        ]

        listener = _FakeListener(
            grouped={"PROMOTION_LIST": [NetworkCapture(url="x", method="GET", status=200, endpoint_type="PROMOTION_LIST", response_body={})]}
        )

        class StubParser:
            def parse_promotion_list(self, response):
                return list(parsed_items)

            def parse_promotion_detail(self, response):
                return None

        provider = NetworkProvider(listener, _price_rules(), parser=StubParser())
        result = provider.acquire(_task())

        assert sorted(result.expected_types) == ["2.9", "9.9", "IAA"]

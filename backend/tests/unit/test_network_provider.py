"""番茄网络响应解析器与 NetworkProvider 单元测试（Phase 5.2-5.3）。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    PromotionAsset,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.network.network_listener import NetworkCapture
from backend.platforms.tomato.network.response_parser import (
    ParsedPromotion,
    TomatoResponseParser,
    _extract_list_items,
    _classify_link_type,
    _safe_float,
    _safe_int,
)
from backend.platforms.tomato.providers.network_provider import NetworkProvider


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 辅助：构造模拟 API 响应
# ---------------------------------------------------------------------------


def _make_promotion_list_response(items: list[dict]) -> dict:
    """模拟标准列表接口响应结构。"""
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "list": items,
            "total": len(items),
            "page": 1,
            "page_size": 20,
        },
    }


def _make_promotion_item(
    *,
    item_id: str = "promo-123",
    drama_id: str = "drama-456",
    drama_name: str = "测试剧",
    link_type: str = "FREE",
    episode: int | None = 2,
    template_id: str | None = "tpl-789",
    template_name: str | None = "2.9元看全集",
    price: float | None = 2.9,
    promotion_url: str = "https://changdupingtai.com/promo/abc123",
    **kwargs: object,
) -> dict:
    data: dict = {
        "id": item_id,
        "drama_id": drama_id,
        "drama_name": drama_name,
        "type": link_type,
        "promotion_url": promotion_url,
        "status": "active",
        "create_time": "2026-08-30 10:00:00",
    }
    if episode is not None:
        data["episode"] = episode
    if template_id is not None:
        data["template_id"] = template_id
    if template_name is not None:
        data["template_name"] = template_name
    if price is not None:
        data["price"] = price
    data.update(kwargs)
    return data


# ---------------------------------------------------------------------------
# 辅助函数：_safe_float / _safe_int
# ---------------------------------------------------------------------------


def test_safe_float_parses_valid_numbers() -> None:
    assert _safe_float("2.9") == 2.9
    assert _safe_float(9.9) == 9.9
    assert _safe_float("10") == 10.0
    assert _safe_float(0) == 0.0


def test_safe_float_returns_none_for_invalid() -> None:
    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float("abc") is None
    assert _safe_float([]) is None


def test_safe_int_parses_valid_numbers() -> None:
    assert _safe_int("2") == 2
    assert _safe_int(5) == 5
    assert _safe_int(3.7) == 3


def test_safe_int_returns_none_for_invalid() -> None:
    assert _safe_int(None) is None
    assert _safe_int("") is None
    assert _safe_int("abc") is None


# ---------------------------------------------------------------------------
# 辅助函数：_extract_list_items
# ---------------------------------------------------------------------------


def test_extract_list_items_from_standard_wrap() -> None:
    resp = _make_promotion_list_response(
        [_make_promotion_item(item_id="p1"), _make_promotion_item(item_id="p2")]
    )
    items = _extract_list_items(resp)
    assert len(items) == 2
    assert items[0]["id"] == "p1"
    assert items[1]["id"] == "p2"


def test_extract_list_items_from_plain_array() -> None:
    resp = [{"id": "a"}, {"id": "b"}]
    items = _extract_list_items(resp)
    assert len(items) == 2


def test_extract_list_items_from_data_array() -> None:
    resp = {"code": 0, "data": [{"id": "x"}, {"id": "y"}]}
    items = _extract_list_items(resp)
    assert len(items) == 2


def test_extract_list_items_empty_for_non_list() -> None:
    assert _extract_list_items({"code": 0, "data": {}}) == []
    assert _extract_list_items({"code": 0}) == []
    assert _extract_list_items(None) == []
    assert _extract_list_items("string") == []


# ---------------------------------------------------------------------------
# 辅助函数：_classify_link_type
# ---------------------------------------------------------------------------


def test_classify_link_type_iaa_by_episode() -> None:
    """含集数字段且类型为免费/IAA 时识别为 IAA。"""
    item = {"type": "FREE", "episode": 2, "promotion_type": "iaa"}
    assert _classify_link_type(item) == "IAA"


def test_classify_link_type_by_price_2_9() -> None:
    item = {"type": "PAID", "price": 2.9, "template_name": "2.9元看全集"}
    assert _classify_link_type(item) == "2.9"


def test_classify_link_type_by_price_9_9() -> None:
    item = {"type": "PAID", "price": 9.9, "template_name": "9.9元看全集"}
    assert _classify_link_type(item) == "9.9"


def test_classify_link_type_by_template_name() -> None:
    """价格缺失时，从模板名推断档位。"""
    item = {"type": "PAID", "template_name": "A测－2.9元看全集"}
    assert _classify_link_type(item) == "2.9"


def test_classify_link_type_unknown() -> None:
    item = {"type": "OTHER", "name": "不知道什么类型"}
    assert _classify_link_type(item) == "UNKNOWN"


# ---------------------------------------------------------------------------
# ParsedPromotion 数据类
# ---------------------------------------------------------------------------


def test_parsed_promotion_has_required_fields() -> None:
    parsed = ParsedPromotion(
        external_drama_id="drama-456",
        promotion_id="promo-123",
        drama_name="测试剧",
        link_type="2.9",
        episode=None,
        template_id="tpl-789",
        template_name="2.9元模板",
        price=2.9,
        promotion_url="https://example.com/promo/abc",
    )

    assert parsed.external_drama_id == "drama-456"
    assert parsed.promotion_id == "promo-123"
    assert parsed.link_type == "2.9"
    assert parsed.price == 2.9


# ---------------------------------------------------------------------------
# TomatoResponseParser
# ---------------------------------------------------------------------------


def test_parser_parse_promotion_list_returns_parsed_items() -> None:
    parser = TomatoResponseParser()
    resp = _make_promotion_list_response(
        [
            _make_promotion_item(item_id="p1", price=2.9, episode=None),
            _make_promotion_item(item_id="p2", link_type="FREE", episode=2, price=None, template_id=None),
        ]
    )

    results = parser.parse_promotion_list(resp)

    assert len(results) == 2
    assert results[0].promotion_id == "p1"
    assert results[0].link_type == "2.9"
    assert results[0].price == 2.9
    assert results[1].promotion_id == "p2"
    assert results[1].link_type == "IAA"
    assert results[1].episode == 2


def test_parser_parse_promotion_list_empty() -> None:
    parser = TomatoResponseParser()
    resp = _make_promotion_list_response([])

    results = parser.parse_promotion_list(resp)

    assert results == []


def test_parser_parse_promotion_detail() -> None:
    parser = TomatoResponseParser()
    resp = {
        "code": 0,
        "data": _make_promotion_item(item_id="p-detail", link_type="PAID", price=9.9, episode=None),
    }

    result = parser.parse_promotion_detail(resp)

    assert result is not None
    assert result.promotion_id == "p-detail"
    assert result.link_type == "9.9"


def test_parser_parse_promotion_detail_none_for_error() -> None:
    parser = TomatoResponseParser()
    assert parser.parse_promotion_detail({"code": 500, "msg": "error"}) is None
    assert parser.parse_promotion_detail({}) is None


def test_parser_parsed_preserves_raw_data() -> None:
    """解析结果应保留原始数据，供后续核对。"""
    parser = TomatoResponseParser()
    raw = _make_promotion_item(item_id="raw-test", link_type="PAID", price=2.9, episode=None, extra_field="custom-value")
    resp = _make_promotion_list_response([raw])

    results = parser.parse_promotion_list(resp)

    assert len(results) == 1
    assert results[0].raw_data.get("extra_field") == "custom-value"


def test_parser_handles_different_field_naming() -> None:
    """字段名有差异时应能启发式匹配。"""
    parser = TomatoResponseParser()
    resp = _make_promotion_list_response([
        {
            "promotionId": "alt-id",
            "dramaId": "alt-drama",
            "dramaTitle": "剧名别名",
            "linkType": "paid",
            "episodes": 5,
            "tplId": "alt-tpl",
            "tplName": "9.9模板",
            "priceAmount": 9.9,
            "shareUrl": "https://alt.example.com/xyz",
        }
    ])

    results = parser.parse_promotion_list(resp)

    assert len(results) == 1
    assert results[0].promotion_id == "alt-id"
    assert results[0].external_drama_id == "alt-drama"
    assert results[0].drama_name == "剧名别名"
    assert results[0].link_type == "9.9"
    assert results[0].price == 9.9


# ---------------------------------------------------------------------------
# NetworkProvider
# ---------------------------------------------------------------------------


class _FakeListener:
    """模拟 NetworkListener，返回预定义的捕获结果。"""

    def __init__(self, captures: list[NetworkCapture]) -> None:
        self._captures = captures

    @property
    def captures(self) -> list[NetworkCapture]:
        return list(self._captures)

    @property
    def grouped_captures(self) -> dict[str, list[NetworkCapture]]:
        groups: dict[str, list[NetworkCapture]] = {}
        for cap in self._captures:
            groups.setdefault(cap.endpoint_type, []).append(cap)
        return groups


def _price_rules() -> list[TemplatePriceRule]:
    return [
        TemplatePriceRule(
            key="iap_2_9",
            target_price=2.9,
            min_price=2.6,
            max_price=5.0,
        ),
        TemplatePriceRule(
            key="iap_9_9",
            target_price=9.9,
            min_price=8.0,
            max_price=12.0,
        ),
    ]


def _make_list_capture(items: list[dict]) -> NetworkCapture:
    return NetworkCapture(
        url="https://changdupingtai.example.com/api/promotion/list",
        method="GET",
        status=200,
        endpoint_type="PROMOTION_LIST",
        response_body=_make_promotion_list_response(items),
    )


def test_network_provider_returns_candidates_from_list_response() -> None:
    """从 PROMOTION_LIST 响应中解析出全部候选。"""
    captures = [
        _make_list_capture([
            _make_promotion_item(item_id="p-iaa", link_type="FREE", episode=2, price=None, template_id=None),
            _make_promotion_item(item_id="p-29", link_type="PAID", price=2.9, episode=None),
            _make_promotion_item(item_id="p-99", link_type="PAID", price=9.9, episode=None),
        ]),
    ]
    listener = _FakeListener(captures)
    provider = NetworkProvider(
        listener=listener,
        price_rules=_price_rules(),
    )

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    result = provider.acquire(task)

    # 应该解析出 3 个 candidate
    assert len(result.candidates) == 3
    # 全部是 NETWORK 方式
    assert all(
        c.acquisition_method == AcquisitionMethod.NETWORK
        for c in result.candidates
    )
    # 三种类型都有
    link_types = {c.link_type for c in result.candidates}
    assert "IAA" in link_types
    assert "2.9" in link_types
    assert "9.9" in link_types


def test_network_provider_no_captures_returns_not_found() -> None:
    """没有捕获到任何推广列表时返回 NOT_FOUND。"""
    listener = _FakeListener([])
    provider = NetworkProvider(listener=listener, price_rules=_price_rules())

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    result = provider.acquire(task)

    assert len(result.candidates) == 0
    assert result.status == "NOT_FOUND"
    assert "network_provider" in result.diagnostics


def test_network_provider_ambiguous_multiple_same_type() -> None:
    """同类型多个结果时标记为 AMBIGUOUS，不自动选第一条。"""
    captures = [
        _make_list_capture([
            _make_promotion_item(item_id="p1", link_type="PAID", price=2.9, template_id="tpl-a", episode=None),
            _make_promotion_item(item_id="p2", link_type="PAID", price=2.9, template_id="tpl-b", episode=None),
        ]),
    ]
    listener = _FakeListener(captures)
    provider = NetworkProvider(listener=listener, price_rules=_price_rules())

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    result = provider.acquire(task)

    # 2.9 档位有多个 → 应出现在 missing 中或标记为 AMBIGUOUS
    assert "2.9" in result.missing
    assert result.missing["2.9"] in {"AMBIGUOUS", "MULTIPLE_CANDIDATES"}


def test_network_provider_diagnostics_contains_endpoint_info() -> None:
    """diagnostics 中应包含 network provider 的详细信息。"""
    captures = [
        _make_list_capture([
            _make_promotion_item(item_id="p1", link_type="PAID", price=2.9, episode=None),
        ]),
    ]
    listener = _FakeListener(captures)
    provider = NetworkProvider(listener=listener, price_rules=_price_rules())

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    result = provider.acquire(task)

    info = result.diagnostics.get("network_provider", {})
    assert info.get("provider") == "NETWORK"
    assert "candidate_count" in info
    assert "endpoint_counts" in info
    assert "parsed_by_type" in info


def test_network_provider_candidates_preserve_raw_data() -> None:
    """Network 来源的 candidate 应保留原始响应数据用于核对。"""
    captures = [
        _make_list_capture([
            _make_promotion_item(item_id="raw-check", link_type="PAID", price=2.9, episode=None, extra_field="custom-value"),
        ]),
    ]
    listener = _FakeListener(captures)
    provider = NetworkProvider(listener=listener, price_rules=_price_rules())

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    result = provider.acquire(task)

    assert len(result.candidates) >= 1
    for c in result.candidates:
        assert isinstance(c.raw_data, dict)
        assert c.raw_data  # 非空


def test_network_provider_uses_price_rules_for_validation() -> None:
    """应使用价格规则校验并精确匹配到 2.9 / 9.9 档位。"""
    captures = [
        _make_list_capture([
            _make_promotion_item(item_id="p1", link_type="PAID", price=2.8, template_id="tpl-a", episode=None),
            _make_promotion_item(item_id="p2", link_type="PAID", price=10.0, template_id="tpl-b", episode=None),
        ]),
    ]
    listener = _FakeListener(captures)
    provider = NetworkProvider(listener=listener, price_rules=_price_rules())

    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    result = provider.acquire(task)

    # 2.8 在 2.6-5.0 范围内，应归类为 2.9
    # 10.0 在 8.0-12.0 范围内，应归类为 9.9
    type_29 = [c for c in result.candidates if c.link_type == "2.9"]
    type_99 = [c for c in result.candidates if c.link_type == "9.9"]
    assert len(type_29) == 1
    assert type_29[0].price == 2.8
    assert len(type_99) == 1
    assert type_99[0].price == 10.0

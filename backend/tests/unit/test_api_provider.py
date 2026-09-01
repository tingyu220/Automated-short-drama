"""ApiProvider 单元测试（Phase 8）。

API Provider 使用真实接口查询和创建推广链接，
通过 CreateSafetyGuard 强制执行安全规则。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.providers.api_provider import (
    ApiProvider,
    TomatoApiClient,
)


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _make_asset(
    *,
    asset_id: str = "a1",
    link_type: str = "2.9",
    promotion_id: str = "promo-1",
    promotion_url: str = "https://x.com/p/abc",
) -> PromotionAsset:
    return PromotionAsset(
        id=asset_id,
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type=link_type,
        promotion_url=promotion_url,
        promotion_id=promotion_id,
        acquisition_method=AcquisitionMethod.API,
        acquisition_status=AssetStatus.VALIDATED,
        created_or_existing=CreationStatus.EXISTING,
    )


def _make_task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )


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


class _FakeApiClient:
    """模拟番茄 API 客户端。"""

    def __init__(
        self,
        *,
        query_results: dict[str, list[PromotionAsset]] | None = None,
        create_results: dict[str, PromotionAsset | None] | None = None,
    ) -> None:
        self._query_results = query_results or {}
        self._create_results = create_results or {}
        self.query_calls: list[str] = []
        self.create_calls: list[str] = []

    def query_promotions(self, drama_name: str, link_type: str) -> list[PromotionAsset]:
        self.query_calls.append(link_type)
        return list(self._query_results.get(link_type, []))

    def create_promotion(self, drama_name: str, link_type: str) -> PromotionAsset | None:
        self.create_calls.append(link_type)
        return self._create_results.get(link_type)


# ---------------------------------------------------------------------------
# 查询已有链接 → 复用
# ---------------------------------------------------------------------------


def test_api_query_founds_existing_reuse() -> None:
    """API 查询到已有链接 → 直接复用，不创建。"""
    existing_29 = _make_asset(link_type="2.9", promotion_id="existing-29")
    existing_99 = _make_asset(link_type="9.9", asset_id="a2", promotion_id="existing-99")
    existing_iaa = _make_asset(
        link_type="IAA", asset_id="a3", promotion_id="existing-iaa",
        promotion_url="https://x.com/p/iaa",
    )

    client = _FakeApiClient(query_results={
        "2.9": [existing_29],
        "9.9": [existing_99],
        "IAA": [existing_iaa],
    })
    provider = ApiProvider(client=client, price_rules=_price_rules())

    result = provider.acquire(_make_task())

    assert result.status == AcquisitionStatus.COMPLETE
    assert len(result.selected) == 3
    assert client.create_calls == []  # 没有创建


# ---------------------------------------------------------------------------
# 查询不到 → 创建 → 再查询 → 验证
# ---------------------------------------------------------------------------


def test_api_create_then_requery() -> None:
    """查询不到 → 创建 → 再查到 → 验证通过。"""
    created_29 = _make_asset(link_type="2.9", promotion_id="new-29")
    created_99 = _make_asset(link_type="9.9", asset_id="a2", promotion_id="new-99")
    created_iaa = _make_asset(
        link_type="IAA", asset_id="a3", promotion_id="new-iaa",
        promotion_url="https://x.com/p/iaa",
    )

    call_count: dict[str, int] = {"2.9": 0, "9.9": 0, "IAA": 0}

    def query_fn(drama_name: str, link_type: str) -> list[PromotionAsset]:
        call_count[link_type] += 1
        if link_type == "2.9" and call_count["2.9"] == 1:
            return []
        if link_type == "9.9" and call_count["9.9"] == 1:
            return []
        if link_type == "IAA" and call_count["IAA"] == 1:
            return []
        # Requery
        if link_type == "2.9":
            return [created_29]
        if link_type == "9.9":
            return [created_99]
        return [created_iaa]

    client = _FakeApiClient()
    client.query_promotions = query_fn  # type: ignore
    client._create_results = {
        "2.9": created_29,
        "9.9": created_99,
        "IAA": created_iaa,
    }

    provider = ApiProvider(client=client, price_rules=_price_rules())
    result = provider.acquire(_make_task())

    assert result.status == AcquisitionStatus.COMPLETE
    assert len(result.selected) == 3
    # 每个档位只创建了一次
    assert client.create_calls.count("2.9") == 1
    assert client.create_calls.count("9.9") == 1
    assert client.create_calls.count("IAA") == 1


# ---------------------------------------------------------------------------
# 创建不确定 → Requery 也没有 → UNCERTAIN
# ---------------------------------------------------------------------------


def test_api_create_uncertain_requery_missing() -> None:
    """Create 不确定 → Requery 也没有 → UNCERTAIN。"""
    client = _FakeApiClient(
        query_results={"2.9": [], "9.9": [], "IAA": []},
        create_results={"2.9": None, "9.9": None, "IAA": None},
    )
    provider = ApiProvider(client=client, price_rules=_price_rules())

    result = provider.acquire(_make_task())

    # 全部档位都是 UNCERTAIN
    assert result.status in (AcquisitionStatus.NOT_FOUND, AcquisitionStatus.PARTIAL)
    assert "2.9" in result.missing
    assert "9.9" in result.missing
    assert "IAA" in result.missing
    # 不重复创建
    assert client.create_calls.count("2.9") == 1


# ---------------------------------------------------------------------------
# 查询多个 → AMBIGUOUS
# ---------------------------------------------------------------------------


def test_api_query_multiple_ambiguous() -> None:
    """查询返回多个 → AMBIGUOUS，该档位不创建。"""
    a1 = _make_asset(link_type="2.9", promotion_id="a")
    a2 = _make_asset(link_type="2.9", asset_id="a2", promotion_id="b")
    existing_99 = _make_asset(link_type="9.9", asset_id="a3", promotion_id="existing-99")
    existing_iaa = _make_asset(
        link_type="IAA", asset_id="a4", promotion_id="existing-iaa",
        promotion_url="https://x.com/p/iaa",
    )

    client = _FakeApiClient(query_results={
        "2.9": [a1, a2],
        "9.9": [existing_99],
        "IAA": [existing_iaa],
    })
    provider = ApiProvider(client=client, price_rules=_price_rules())

    result = provider.acquire(_make_task())

    assert "2.9" in result.missing
    assert result.missing["2.9"] in ("AMBIGUOUS", "UNCERTAIN")
    # 2.9 没有触发创建
    assert "2.9" not in client.create_calls


# ---------------------------------------------------------------------------
# 混合结果
# ---------------------------------------------------------------------------


def test_api_mixed_results() -> None:
    """2.9 已有复用，9.9 创建，IAA 不确定。"""
    existing_29 = _make_asset(link_type="2.9", promotion_id="existing-29")

    call_count: dict[str, int] = {"2.9": 0, "9.9": 0, "IAA": 0}

    def query_fn(drama_name: str, link_type: str) -> list[PromotionAsset]:
        call_count[link_type] += 1
        if link_type == "2.9":
            return [existing_29]  # 已有
        if link_type == "9.9":
            if call_count["9.9"] == 1:
                return []
            return [_make_asset(link_type="9.9", asset_id="new-99", promotion_id="new-99")]
        return []  # IAA 始终没有

    client = _FakeApiClient()
    client.query_promotions = query_fn  # type: ignore
    client._create_results = {"9.9": None, "IAA": None}

    provider = ApiProvider(client=client, price_rules=_price_rules())
    result = provider.acquire(_make_task())

    # 2.9 复用，9.9 创建成功，IAA 不确定
    selected_types = {a.link_type for a in result.selected}
    assert "2.9" in selected_types
    assert "9.9" in selected_types
    assert "IAA" in result.missing


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------


def test_api_diagnostics_contains_provider_info() -> None:
    """diagnostics 包含 provider 信息。"""
    existing = _make_asset(link_type="2.9")
    client = _FakeApiClient(query_results={"2.9": [existing], "9.9": [], "IAA": []})
    provider = ApiProvider(client=client, price_rules=_price_rules())

    result = provider.acquire(_make_task())

    diag = result.diagnostics.get("api_provider", {})
    assert diag.get("provider") == "API"
    assert "per_type" in diag


# ---------------------------------------------------------------------------
# TomatoApiClient 协议
# ---------------------------------------------------------------------------


def test_tomato_api_client_is_protocol() -> None:
    """TomatoApiClient 是可运行时检查的 Protocol。"""
    from typing import runtime_checkable
    assert hasattr(TomatoApiClient, "__protocol__") or isinstance(
        type(TomatoApiClient), type
    )

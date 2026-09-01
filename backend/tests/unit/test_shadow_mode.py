"""Shadow Mode 对比器与 Provider 单元测试（Phase 7）。

SHADOW 模式：Legacy DOM 走生产，Network V2 只观察，对比记录差异。
差异类型：LEGACY_MISSING_V2_FOUND / LEGACY_FOUND_V2_MISSING / URL_MISMATCH / AMBIGUOUS
Critical mismatch = 0 才能通过验收。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.shadow_comparator import (
    DiscrepancyType,
    ShadowComparison,
    ShadowComparator,
)
from backend.domain.acquisition.shadow_provider import (
    ShadowMode,
    ShadowModeProvider,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
)
from backend.domain.tasks.drama_task import DramaTask


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 辅助：构造 PromotionAsset
# ---------------------------------------------------------------------------


def _make_asset(
    *,
    asset_id: str = "a1",
    link_type: str = "2.9",
    promotion_url: str = "https://example.com/promo/abc",
    external_drama_id: str | None = "drama-123",
    promotion_id: str | None = "promo-1",
    drama_name: str = "测试剧",
    price: float | None = 2.9,
    acquisition_method: AcquisitionMethod = AcquisitionMethod.LEGACY,
    acquisition_status: AssetStatus = AssetStatus.VALIDATED,
) -> PromotionAsset:
    return PromotionAsset(
        id=asset_id,
        task_id="task-1",
        source_platform="TOMATO",
        drama_name=drama_name,
        link_type=link_type,
        promotion_url=promotion_url,
        external_drama_id=external_drama_id,
        promotion_id=promotion_id,
        price=price,
        acquisition_method=acquisition_method,
        acquisition_status=acquisition_status,
        created_or_existing=CreationStatus.EXISTING,
    )


def _make_legacy_result(
    *,
    selected: list[PromotionAsset] | None = None,
    missing: dict[str, str] | None = None,
) -> AcquisitionResult:
    """构造 Legacy DOM 采集结果。"""
    return AcquisitionResult(
        status=AcquisitionStatus.COMPLETE if selected else AcquisitionStatus.NOT_FOUND,
        expected_types=[a.link_type for a in (selected or [])],
        candidates=selected or [],
        selected=selected or [],
        missing=missing or {},
        diagnostics={"provider": "LEGACY_DOM"},
    )


def _make_network_result(
    *,
    selected: list[PromotionAsset] | None = None,
    missing: dict[str, str] | None = None,
    candidates: list[PromotionAsset] | None = None,
) -> AcquisitionResult:
    """构造 Network V2 采集结果。"""
    return AcquisitionResult(
        status=AcquisitionStatus.COMPLETE if selected else AcquisitionStatus.NOT_FOUND,
        expected_types=[a.link_type for a in (selected or [])],
        candidates=candidates or selected or [],
        selected=selected or [],
        missing=missing or {},
        diagnostics={"provider": "NETWORK"},
    )


def _make_task(drama_name: str = "测试剧") -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name=drama_name,
        platform="TOMATO",
        available_time=TARGET_TIME,
    )


# ---------------------------------------------------------------------------
# DiscrepancyType 枚举
# ---------------------------------------------------------------------------


def test_discrepancy_types_exist() -> None:
    """四种差异类型全部存在。"""
    assert DiscrepancyType.LEGACY_MISSING_V2_FOUND
    assert DiscrepancyType.LEGACY_FOUND_V2_MISSING
    assert DiscrepancyType.URL_MISMATCH
    assert DiscrepancyType.AMBIGUOUS


# ---------------------------------------------------------------------------
# ShadowComparator: 完全一致
# ---------------------------------------------------------------------------


def test_compare_both_found_same_url_no_discrepancy() -> None:
    """Legacy 和 V2 都找到同链接、同 URL → 无差异。"""
    asset = _make_asset(link_type="2.9", promotion_url="https://x.com/p/abc")
    legacy = _make_legacy_result(selected=[asset])
    v2 = _make_network_result(selected=[_make_asset(
        link_type="2.9", promotion_url="https://x.com/p/abc",
        acquisition_method=AcquisitionMethod.NETWORK,
    )])

    comparison = ShadowComparator().compare(legacy, v2)

    assert comparison.discrepancies == []
    assert comparison.critical_mismatch_count == 0


def test_compare_both_empty_no_discrepancy() -> None:
    """Legacy 和 V2 都没找到 → 无差异。"""
    legacy = _make_legacy_result(selected=[])
    v2 = _make_network_result(selected=[])

    comparison = ShadowComparator().compare(legacy, v2)

    assert comparison.discrepancies == []
    assert comparison.critical_mismatch_count == 0


# ---------------------------------------------------------------------------
# ShadowComparator: LEGACY_MISSING_V2_FOUND
# ---------------------------------------------------------------------------


def test_compare_legacy_missing_v2_found() -> None:
    """Legacy 没找到 9.9，但 V2 找到了 → LEGACY_MISSING_V2_FOUND。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    v2 = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
        _make_asset(
            asset_id="v2-99", link_type="9.9", promotion_url="https://x.com/p/99",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])

    comparison = ShadowComparator().compare(legacy, v2)

    found = [d for d in comparison.discrepancies if d.type == DiscrepancyType.LEGACY_MISSING_V2_FOUND]
    assert len(found) == 1
    assert found[0].link_type == "9.9"


# ---------------------------------------------------------------------------
# ShadowComparator: LEGACY_FOUND_V2_MISSING
# ---------------------------------------------------------------------------


def test_compare_legacy_found_v2_missing() -> None:
    """Legacy 找到了 2.9，但 V2 没找到 → LEGACY_FOUND_V2_MISSING。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
        _make_asset(asset_id="leg-99", link_type="9.9", promotion_url="https://x.com/p/99"),
    ])
    v2 = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])

    comparison = ShadowComparator().compare(legacy, v2)

    found = [d for d in comparison.discrepancies if d.type == DiscrepancyType.LEGACY_FOUND_V2_MISSING]
    assert len(found) == 1
    assert found[0].link_type == "9.9"


# ---------------------------------------------------------------------------
# ShadowComparator: URL_MISMATCH
# ---------------------------------------------------------------------------


def test_compare_url_mismatch_is_critical() -> None:
    """同档位但 URL 不同 → URL_MISMATCH，属于 Critical。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/legacy-29"),
    ])
    v2 = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/v2-29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])

    comparison = ShadowComparator().compare(legacy, v2)

    found = [d for d in comparison.discrepancies if d.type == DiscrepancyType.URL_MISMATCH]
    assert len(found) == 1
    assert found[0].link_type == "2.9"
    assert found[0].is_critical is True
    assert comparison.critical_mismatch_count == 1


# ---------------------------------------------------------------------------
# ShadowComparator: AMBIGUOUS
# ---------------------------------------------------------------------------


def test_compare_v2_ambiguous_is_discrepancy() -> None:
    """V2 返回 AMBIGUOUS → 记录为 AMBIGUOUS 差异。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    v2 = _make_network_result(
        selected=[],
        missing={"2.9": "AMBIGUOUS"},
        candidates=[
            _make_asset(
                asset_id="v2-a", link_type="2.9",
                promotion_url="https://x.com/p/a",
                acquisition_method=AcquisitionMethod.NETWORK,
                acquisition_status=AssetStatus.AMBIGUOUS,
            ),
            _make_asset(
                asset_id="v2-b", link_type="2.9",
                promotion_url="https://x.com/p/b",
                acquisition_method=AcquisitionMethod.NETWORK,
                acquisition_status=AssetStatus.AMBIGUOUS,
            ),
        ],
    )

    comparison = ShadowComparator().compare(legacy, v2)

    found = [d for d in comparison.discrepancies if d.type == DiscrepancyType.AMBIGUOUS]
    assert len(found) == 1
    assert found[0].link_type == "2.9"


# ---------------------------------------------------------------------------
# ShadowComparator: 多档位混合差异
# ---------------------------------------------------------------------------


def test_compare_mixed_discrepancies() -> None:
    """多档位混合差异：2.9 一致，9.9 URL 不同，IAA Legacy 有 V2 没有。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
        _make_asset(asset_id="leg-99", link_type="9.9", promotion_url="https://x.com/p/leg-99"),
        _make_asset(asset_id="leg-iaa", link_type="IAA", promotion_url="https://x.com/p/iaa"),
    ])
    v2 = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
        _make_asset(
            asset_id="v2-99", link_type="9.9", promotion_url="https://x.com/p/v2-99",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])

    comparison = ShadowComparator().compare(legacy, v2)

    assert len(comparison.discrepancies) == 2
    types = {d.type for d in comparison.discrepancies}
    assert DiscrepancyType.URL_MISMATCH in types  # 9.9 URL 不同
    assert DiscrepancyType.LEGACY_FOUND_V2_MISSING in types  # IAA Legacy 有 V2 没有


# ---------------------------------------------------------------------------
# ShadowComparator: Critical mismatch 判定
# ---------------------------------------------------------------------------


def test_critical_mismatch_count_zero_when_all_match() -> None:
    """完全一致 → critical = 0。"""
    asset = _make_asset(link_type="2.9", promotion_url="https://x.com/p/29")
    legacy = _make_legacy_result(selected=[asset])
    v2 = _make_network_result(selected=[_make_asset(
        link_type="2.9", promotion_url="https://x.com/p/29",
        acquisition_method=AcquisitionMethod.NETWORK,
    )])

    comparison = ShadowComparator().compare(legacy, v2)

    assert comparison.critical_mismatch_count == 0
    assert comparison.is_passing is True


def test_critical_mismatch_url_mismatch_counts() -> None:
    """URL_MISMATCH 是 critical。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/leg"),
    ])
    v2 = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/v2",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])

    comparison = ShadowComparator().compare(legacy, v2)

    assert comparison.critical_mismatch_count == 1
    assert comparison.is_passing is False


def test_legacy_missing_v2_found_not_critical() -> None:
    """Legacy 漏链接但 V2 找到了 → 非 critical（V2 更好）。"""
    legacy = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    v2 = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
        _make_asset(
            asset_id="v2-99", link_type="9.9", promotion_url="https://x.com/p/99",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])

    comparison = ShadowComparator().compare(legacy, v2)

    assert comparison.critical_mismatch_count == 0
    assert comparison.is_passing is True


# ---------------------------------------------------------------------------
# ShadowMode 枚举
# ---------------------------------------------------------------------------


def test_shadow_mode_values() -> None:
    assert ShadowMode.LEGACY
    assert ShadowMode.SHADOW
    assert ShadowMode.V2


# ---------------------------------------------------------------------------
# ShadowModeProvider: LEGACY 模式
# ---------------------------------------------------------------------------


class _FakeProvider:
    """模拟 Provider。"""

    def __init__(self, result: AcquisitionResult) -> None:
        self._result = result
        self.call_count = 0

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        self.call_count += 1
        return self._result


def test_shadow_provider_legacy_mode_only_calls_legacy() -> None:
    """LEGACY 模式只调用 Legacy Provider。"""
    legacy_result = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    legacy = _FakeProvider(legacy_result)
    network = _FakeProvider(_make_network_result(selected=[]))

    provider = ShadowModeProvider(
        legacy=legacy,
        network=network,
        mode=ShadowMode.LEGACY,
    )

    result = provider.acquire(_make_task())

    assert legacy.call_count == 1
    assert network.call_count == 0
    assert result.diagnostics.get("shadow_mode") == "LEGACY"


def test_shadow_provider_v2_mode_only_calls_network() -> None:
    """V2 模式只调用 Network Provider。"""
    legacy = _FakeProvider(_make_legacy_result(selected=[]))
    network_result = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])
    network = _FakeProvider(network_result)

    provider = ShadowModeProvider(
        legacy=legacy,
        network=network,
        mode=ShadowMode.V2,
    )

    result = provider.acquire(_make_task())

    assert legacy.call_count == 0
    assert network.call_count == 1
    assert result.diagnostics.get("shadow_mode") == "V2"


# ---------------------------------------------------------------------------
# ShadowModeProvider: SHADOW 模式
# ---------------------------------------------------------------------------


def test_shadow_provider_shadow_mode_calls_both() -> None:
    """SHADOW 模式同时调用 Legacy 和 Network。"""
    legacy_result = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    legacy = _FakeProvider(legacy_result)
    network_result = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])
    network = _FakeProvider(network_result)

    provider = ShadowModeProvider(
        legacy=legacy,
        network=network,
        mode=ShadowMode.SHADOW,
    )

    result = provider.acquire(_make_task())

    assert legacy.call_count == 1
    assert network.call_count == 1
    assert result.diagnostics.get("shadow_mode") == "SHADOW"


def test_shadow_provider_shadow_returns_legacy_result_for_production() -> None:
    """SHADOW 模式返回 Legacy 结果作为生产结果。"""
    legacy_asset = _make_asset(
        asset_id="leg-29", link_type="2.9",
        promotion_url="https://x.com/p/legacy-29",
    )
    legacy_result = _make_legacy_result(selected=[legacy_asset])
    legacy = _FakeProvider(legacy_result)
    network = _FakeProvider(_make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/v2-29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ]))

    provider = ShadowModeProvider(
        legacy=legacy,
        network=network,
        mode=ShadowMode.SHADOW,
    )

    result = provider.acquire(_make_task())

    # 生产结果用 Legacy 的
    assert result.selected == [legacy_asset]
    assert result.selected[0].promotion_url == "https://x.com/p/legacy-29"


def test_shadow_provider_includes_comparison_in_diagnostics() -> None:
    """SHADOW 模式 diagnostics 中包含对比结果。"""
    legacy_result = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    legacy = _FakeProvider(legacy_result)
    network_result = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/v2-different",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])
    network = _FakeProvider(network_result)

    provider = ShadowModeProvider(
        legacy=legacy,
        network=network,
        mode=ShadowMode.SHADOW,
    )

    result = provider.acquire(_make_task())

    shadow_diag = result.diagnostics.get("shadow_comparison", {})
    assert shadow_diag.get("discrepancy_count") == 1
    assert shadow_diag.get("critical_mismatch_count") == 1
    assert shadow_diag.get("is_passing") is False
    assert "discrepancies" in shadow_diag


def test_shadow_provider_shadow_no_discrepancies_passes() -> None:
    """SHADOW 模式无差异 → is_passing = True。"""
    legacy_result = _make_legacy_result(selected=[
        _make_asset(link_type="2.9", promotion_url="https://x.com/p/29"),
    ])
    legacy = _FakeProvider(legacy_result)
    network_result = _make_network_result(selected=[
        _make_asset(
            link_type="2.9", promotion_url="https://x.com/p/29",
            acquisition_method=AcquisitionMethod.NETWORK,
        ),
    ])
    network = _FakeProvider(network_result)

    provider = ShadowModeProvider(
        legacy=legacy,
        network=network,
        mode=ShadowMode.SHADOW,
    )

    result = provider.acquire(_make_task())

    shadow_diag = result.diagnostics.get("shadow_comparison", {})
    assert shadow_diag.get("is_passing") is True
    assert shadow_diag.get("critical_mismatch_count") == 0

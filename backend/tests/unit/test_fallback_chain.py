"""FallbackChainProvider 单元测试（Phase 8）。

Provider 优先级：API → Network → DOM → Manual
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.fallback_chain import FallbackChainProvider
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
)
from backend.domain.tasks.drama_task import DramaTask


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _make_asset(
    *,
    asset_id: str = "a1",
    link_type: str = "2.9",
    method: AcquisitionMethod = AcquisitionMethod.API,
) -> PromotionAsset:
    return PromotionAsset(
        id=asset_id,
        task_id="task-1",
        source_platform="TOMATO",
        drama_name="测试剧",
        link_type=link_type,
        promotion_url=f"https://x.com/p/{asset_id}",
        acquisition_method=method,
        acquisition_status=AssetStatus.VALIDATED,
        created_or_existing=CreationStatus.EXISTING,
    )


def _make_result(
    *,
    selected: list[PromotionAsset] | None = None,
    status: str = AcquisitionStatus.COMPLETE,
    missing: dict[str, str] | None = None,
) -> AcquisitionResult:
    return AcquisitionResult(
        status=status,
        expected_types=[a.link_type for a in (selected or [])],
        candidates=selected or [],
        selected=selected or [],
        missing=missing or {},
    )


def _make_task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )


class _FakeProvider:
    """可控的模拟 Provider。"""

    def __init__(self, name: str, result: AcquisitionResult) -> None:
        self.name = name
        self._result = result
        self.call_count = 0

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        self.call_count += 1
        r = self._result
        return AcquisitionResult(
            status=r.status,
            expected_types=list(r.expected_types),
            candidates=list(r.candidates),
            selected=list(r.selected),
            missing=dict(r.missing),
            diagnostics=dict(r.diagnostics),
            warnings=list(r.warnings),
        )


# ---------------------------------------------------------------------------
# API 优先
# ---------------------------------------------------------------------------


def test_api_succeeds_no_fallback() -> None:
    """API 成功 → 不降级到 Network / DOM。"""
    api_asset = _make_asset(asset_id="api-1", method=AcquisitionMethod.API)
    api = _FakeProvider("API", _make_result(selected=[api_asset]))
    network = _FakeProvider("NETWORK", _make_result(selected=[]))
    dom = _FakeProvider("DOM", _make_result(selected=[]))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    assert api.call_count == 1
    assert network.call_count == 0
    assert dom.call_count == 0
    assert len(result.selected) == 1
    assert result.selected[0].id == "api-1"


# ---------------------------------------------------------------------------
# API 失败 → Network 降级
# ---------------------------------------------------------------------------


def test_api_fails_fallback_to_network() -> None:
    """API 没找到 → 降级到 Network。"""
    api = _FakeProvider("API", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))
    net_asset = _make_asset(asset_id="net-1", method=AcquisitionMethod.NETWORK)
    network = _FakeProvider("NETWORK", _make_result(selected=[net_asset]))
    dom = _FakeProvider("DOM", _make_result(selected=[]))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    assert api.call_count == 1
    assert network.call_count == 1
    assert len(result.selected) == 1
    assert result.selected[0].id == "net-1"


# ---------------------------------------------------------------------------
# API + Network 都失败 → DOM 降级
# ---------------------------------------------------------------------------


def test_api_network_fail_fallback_to_dom() -> None:
    """API 和 Network 都没找到 → 降级到 DOM。"""
    api = _FakeProvider("API", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))
    network = _FakeProvider("NETWORK", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))
    dom_asset = _make_asset(asset_id="dom-1", method=AcquisitionMethod.LEGACY)
    dom = _FakeProvider("DOM", _make_result(selected=[dom_asset]))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    assert api.call_count == 1
    assert network.call_count == 1
    assert dom.call_count == 1
    assert len(result.selected) == 1
    assert result.selected[0].id == "dom-1"


# ---------------------------------------------------------------------------
# 全部失败 → NOT_FOUND
# ---------------------------------------------------------------------------


def test_all_providers_fail_returns_not_found() -> None:
    """所有 Provider 都没找到 → NOT_FOUND。"""
    api = _FakeProvider("API", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))
    network = _FakeProvider("NETWORK", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))
    dom = _FakeProvider("DOM", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    assert result.status == AcquisitionStatus.NOT_FOUND
    assert len(result.selected) == 0


# ---------------------------------------------------------------------------
# 部分成功：API 找到 2.9，Network 补 9.9
# ---------------------------------------------------------------------------


def test_partial_success_merges_results() -> None:
    """API 找到 2.9，Network 找到 9.9 → 合并结果。"""
    api_asset = _make_asset(asset_id="api-29", link_type="2.9", method=AcquisitionMethod.API)
    api = _FakeProvider("API", _make_result(
        selected=[api_asset],
        status=AcquisitionStatus.PARTIAL,
        missing={"9.9": "NOT_FOUND"},
    ))
    net_asset = _make_asset(asset_id="net-99", link_type="9.9", method=AcquisitionMethod.NETWORK)
    network = _FakeProvider("NETWORK", _make_result(selected=[net_asset]))
    dom = _FakeProvider("DOM", _make_result(selected=[]))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    assert len(result.selected) == 2
    types = {a.link_type for a in result.selected}
    assert "2.9" in types
    assert "9.9" in types


# ---------------------------------------------------------------------------
# 不重复选择同一档位
# ---------------------------------------------------------------------------


def test_no_duplicate_selection_same_type() -> None:
    """API 和 Network 都找到 2.9 → 只取 API 的（优先级高）。"""
    api_asset = _make_asset(asset_id="api-29", link_type="2.9", method=AcquisitionMethod.API)
    api = _FakeProvider("API", _make_result(selected=[api_asset]))
    net_asset = _make_asset(asset_id="net-29", link_type="2.9", method=AcquisitionMethod.NETWORK)
    network = _FakeProvider("NETWORK", _make_result(selected=[net_asset]))
    dom = _FakeProvider("DOM", _make_result(selected=[]))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    selected_29 = [a for a in result.selected if a.link_type == "2.9"]
    assert len(selected_29) == 1
    assert selected_29[0].id == "api-29"  # 取 API 的


# ---------------------------------------------------------------------------
# diagnostics 包含 provider 调用链
# ---------------------------------------------------------------------------


def test_diagnostics_contains_fallback_trace() -> None:
    """diagnostics 中包含 fallback 调用链信息。"""
    api = _FakeProvider("API", _make_result(selected=[], status=AcquisitionStatus.NOT_FOUND))
    net_asset = _make_asset(asset_id="net-1", method=AcquisitionMethod.NETWORK)
    network = _FakeProvider("NETWORK", _make_result(selected=[net_asset]))
    dom = _FakeProvider("DOM", _make_result(selected=[]))

    chain = FallbackChainProvider([api, network, dom])
    result = chain.acquire(_make_task())

    diag = result.diagnostics.get("fallback_chain", {})
    assert "providers_tried" in diag
    assert "API" in diag["providers_tried"]
    assert "NETWORK" in diag["providers_tried"]
    assert diag.get("final_provider") == "NETWORK"


# ---------------------------------------------------------------------------
# 空链
# ---------------------------------------------------------------------------


def test_empty_chain_returns_not_found() -> None:
    """没有 Provider → NOT_FOUND。"""
    chain = FallbackChainProvider([])
    result = chain.acquire(_make_task())

    assert result.status == AcquisitionStatus.NOT_FOUND
    assert len(result.selected) == 0

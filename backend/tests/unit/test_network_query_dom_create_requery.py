"""验证 DOM 搜索 → Network 确认流程。"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.scoped_network_provider import ScopedNetworkProvider
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask


class _FakeListener:
    def __init__(self):
        self.scope_calls = []

    def begin_scope(self, task_id):
        self.scope_calls.append(("begin", task_id))

    def end_scope(self):
        self.scope_calls.append(("end", None))

    @property
    def scope_task_id(self):
        return None


class _StubProvider:
    def __init__(self, name, result):
        self.name = name
        self._result = result
        self.call_count = 0

    def acquire(self, task):
        self.call_count += 1
        if callable(self._result):
            return self._result(self.call_count)
        return self._result


def _price_rules():
    return [
        TemplatePriceRule(target_price=2.9, min_price=2.0, max_price=5.0, key="iap_2_9"),
        TemplatePriceRule(target_price=9.9, min_price=7.0, max_price=15.0, key="iap_9_9"),
    ]


def _task():
    return DramaTask(
        id="t1",
        sheet_row=1,
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links={},
    )


def _asset(link_type, url="aweme://playlet?x=1", created=False):
    return PromotionAsset(
        id=str(uuid4()),
        task_id="t1",
        source_platform="TOMATO",
        drama_name="剧A",
        link_type=link_type,
        promotion_url=url,
        promotion_id=f"p-{link_type}",
        external_drama_id="drama-1",
        acquisition_method=AcquisitionMethod.NETWORK,
        acquisition_status=AssetStatus.VALIDATED,
        verification_status=VerificationStatus.VALIDATED,
        created_or_existing=CreationStatus.CREATED if created else CreationStatus.EXISTING,
    )


class TestScopedNetworkProvider:
    """DOM 搜索 → Network 确认流程。"""

    def test_scope_lifecycle_called(self):
        """acquire 调用 begin_scope 和 end_scope。"""
        listener = _FakeListener()

        all_found = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            selected=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            missing={},
        )

        provider = ScopedNetworkProvider(
            listener=listener,
            network_provider=_StubProvider("NETWORK", all_found),
            legacy_provider=_StubProvider("DOM", all_found),
        )
        provider.acquire(_task())

        assert ("begin", "t1") in listener.scope_calls
        assert ("end", None) in listener.scope_calls

    def test_dom_all_found_no_create_skips_network(self):
        """DOM 全部找到且无创建 → 跳过 Network，直接返回。"""
        listener = _FakeListener()

        all_found = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            selected=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            missing={},
        )

        network = _StubProvider("NETWORK", all_found)

        provider = ScopedNetworkProvider(
            listener=listener,
            network_provider=network,
            legacy_provider=_StubProvider("DOM", all_found),
        )
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE
        assert network.call_count == 0  # Network was skipped

    def test_dom_created_triggers_network_confirm(self):
        """DOM 有创建操作 → 触发 Network 确认。"""
        listener = _FakeListener()

        dom_result = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA", created=True), _asset("2.9", created=True), _asset("9.9", created=True)],
            selected=[_asset("IAA", created=True), _asset("2.9", created=True), _asset("9.9", created=True)],
            missing={},
        )

        network_result = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            selected=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            missing={},
        )

        network = _StubProvider("NETWORK", network_result)

        provider = ScopedNetworkProvider(
            listener=listener,
            network_provider=network,
            legacy_provider=_StubProvider("DOM", dom_result),
        )
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE
        assert network.call_count == 1  # Network was called for confirmation

    def test_dom_partial_triggers_network_supplement(self):
        """DOM 部分找到 → Network 补充缺失。"""
        listener = _FakeListener()

        dom_result = AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA")],
            selected=[_asset("IAA")],
            missing={"2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
        )

        network_result = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            selected=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            missing={},
        )

        provider = ScopedNetworkProvider(
            listener=listener,
            network_provider=_StubProvider("NETWORK", network_result),
            legacy_provider=_StubProvider("DOM", dom_result),
        )
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE

    def test_both_missing_returns_result_uncertain(self):
        """DOM 和 Network 都缺失 → RESULT_UNCERTAIN。"""
        listener = _FakeListener()

        partial = AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA")],
            selected=[_asset("IAA")],
            missing={"2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
        )

        provider = ScopedNetworkProvider(
            listener=listener,
            network_provider=_StubProvider("NETWORK", partial),
            legacy_provider=_StubProvider("DOM", partial),
        )
        result = provider.acquire(_task())

        assert result.status != AcquisitionStatus.COMPLETE
        assert "RESULT_UNCERTAIN" in result.diagnostics.get("scoped_provider", {}).get("final_status", "")

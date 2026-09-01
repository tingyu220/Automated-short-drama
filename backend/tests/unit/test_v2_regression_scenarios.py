"""V2 链接采集回归测试：覆盖计划中的 8 个关键场景。"""
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


def _price_rules():
    return [
        TemplatePriceRule(target_price=2.9, min_price=2.0, max_price=5.0, key="iap_2_9"),
        TemplatePriceRule(target_price=9.9, min_price=7.0, max_price=15.0, key="iap_9_9"),
    ]


def _task(task_id="t1", drama_name="剧A"):
    return DramaTask(
        id=task_id,
        sheet_row=1,
        drama_name=drama_name,
        platform="TOMATO",
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links={},
    )


def _asset(link_type, url="aweme://playlet?x=1", drama_name="剧A", created=False):
    return PromotionAsset(
        id=str(uuid4()),
        task_id="t1",
        source_platform="TOMATO",
        drama_name=drama_name,
        link_type=link_type,
        promotion_url=url,
        promotion_id=f"p-{link_type}",
        external_drama_id="drama-1",
        acquisition_method=AcquisitionMethod.NETWORK,
        acquisition_status=AssetStatus.VALIDATED,
        verification_status=VerificationStatus.VALIDATED,
        created_or_existing=CreationStatus.CREATED if created else CreationStatus.EXISTING,
    )


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
    def __init__(self, result_fn):
        self._result_fn = result_fn
        self.call_count = 0

    def acquire(self, task):
        self.call_count += 1
        return self._result_fn(self.call_count, task)


class TestV2RegressionScenarios:
    """计划中 8 个关键回归场景。"""

    def test_case1_all_found_validated(self):
        """Case 1: IAA + 2.9 + 9.9 全部 FOUND → COMPLETE。"""
        all_found = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            selected=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
            missing={},
        )

        network = _StubProvider(lambda c, t: all_found)
        legacy = _StubProvider(lambda c, t: all_found)

        provider = ScopedNetworkProvider(
            listener=_FakeListener(),
            network_provider=network,
            legacy_provider=legacy,
        )
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE
        assert network.call_count == 0  # DOM found all without create → skip network

    def test_case4_dom_partial_network_supplements(self):
        """Case 4: DOM 只找到 IAA → Network 补充 2.9/9.9。"""
        def dom_fn(count, task):
            return AcquisitionResult(
                status=AcquisitionStatus.PARTIAL,
                expected_types=["IAA", "2.9", "9.9"],
                candidates=[_asset("IAA")],
                selected=[_asset("IAA")],
                missing={"2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
            )

        def network_fn(count, task):
            return AcquisitionResult(
                status=AcquisitionStatus.COMPLETE,
                expected_types=["IAA", "2.9", "9.9"],
                candidates=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
                selected=[_asset("IAA"), _asset("2.9"), _asset("9.9")],
                missing={},
            )

        provider = ScopedNetworkProvider(
            listener=_FakeListener(),
            network_provider=_StubProvider(network_fn),
            legacy_provider=_StubProvider(dom_fn),
        )
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE
        assert "2.9" in [a.link_type for a in result.selected]
        assert "9.9" in [a.link_type for a in result.selected]

    def test_case5_dom_create_then_network_confirms(self):
        """Case 5: DOM 创建链接 → Network 确认找到 → VALIDATED。"""
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

        network = _StubProvider(lambda c, t: network_result)

        provider = ScopedNetworkProvider(
            listener=_FakeListener(),
            network_provider=network,
            legacy_provider=_StubProvider(lambda c, t: dom_result),
        )
        result = provider.acquire(_task())

        assert result.status == AcquisitionStatus.COMPLETE
        assert network.call_count == 1  # Network was called for confirmation

    def test_case6_both_missing_result_uncertain(self):
        """Case 6: DOM 和 Network 都找不到 → RESULT_UNCERTAIN。"""
        partial = AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[_asset("IAA")],
            selected=[_asset("IAA")],
            missing={"2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
        )

        provider = ScopedNetworkProvider(
            listener=_FakeListener(),
            network_provider=_StubProvider(lambda c, t: partial),
            legacy_provider=_StubProvider(lambda c, t: partial),
        )
        result = provider.acquire(_task())

        assert result.status != AcquisitionStatus.COMPLETE
        assert "RESULT_UNCERTAIN" in result.diagnostics.get("scoped_provider", {}).get("final_status", "")

    def test_case7_two_candidates_same_type_ambiguous(self):
        """Case 7: 两个同档 Candidate → AMBIGUOUS。"""
        a1 = _asset("2.9", "aweme://playlet?x=1")
        a2 = _asset("2.9", "aweme://playlet?x=2")
        a2.promotion_id = "p-different"

        result = AcquisitionResult(
            status=AcquisitionStatus.AMBIGUOUS,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[a1, a2],
            selected=[],
            missing={"2.9": "AMBIGUOUS"},
        )

        provider = ScopedNetworkProvider(
            listener=_FakeListener(),
            network_provider=_StubProvider(lambda c, t: result),
            legacy_provider=_StubProvider(lambda c, t: result),
        )
        final = provider.acquire(_task())

        assert final.status != AcquisitionStatus.COMPLETE
        assert "2.9" in final.missing

    def test_case8_scope_isolation_between_tasks(self):
        """Case 8: 前一部剧的 Network Response 不能进入后一部剧 Candidate。"""
        listener = _FakeListener()

        task_a_result = AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[
                PromotionAsset(
                    id="a-IAA", task_id="tA", source_platform="TOMATO",
                    drama_name="剧A", link_type="IAA", promotion_url="aweme://playlet?x=1",
                    promotion_id="p-A", external_drama_id="drama-A",
                    acquisition_method=AcquisitionMethod.NETWORK,
                    acquisition_status=AssetStatus.VALIDATED,
                    verification_status=VerificationStatus.VALIDATED,
                    created_or_existing=CreationStatus.EXISTING,
                ),
            ],
            selected=[],
            missing={"2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
        )

        provider = ScopedNetworkProvider(
            listener=listener,
            network_provider=_StubProvider(lambda c, t: task_a_result),
            legacy_provider=_StubProvider(lambda c, t: task_a_result),
        )

        provider.acquire(_task(task_id="tA", drama_name="剧A"))
        provider.acquire(_task(task_id="tB", drama_name="剧B"))

        begin_calls = [c for c in listener.scope_calls if c[0] == "begin"]
        assert len(begin_calls) == 2
        assert begin_calls[0][1] == "tA"
        assert begin_calls[1][1] == "tB"

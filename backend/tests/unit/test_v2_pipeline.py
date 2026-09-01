"""V2 Acquisition Pipeline 单元测试（Phase 9）。

V2 管线完整编排：
Provider 链 acquire → Validator validate → 冻结 link_set → READY / MANUAL_REVIEW
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.acquisition.v2_pipeline import (
    PipelineOutcome,
    V2AcquisitionPipeline,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.tasks.drama_task import DramaTask


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _make_asset(
    *,
    asset_id: str = "a1",
    link_type: str = "2.9",
    promotion_url: str = "aweme://playlet?advertise_param=abc123",
    drama_name: str = "测试剧",
    method: AcquisitionMethod = AcquisitionMethod.API,
    task_id: str = "task-1",
    platform: str = "TOMATO",
    acquisition_status: AssetStatus = AssetStatus.VALIDATED,
    verification_status: VerificationStatus = VerificationStatus.VALIDATED,
) -> PromotionAsset:
    return PromotionAsset(
        id=asset_id,
        task_id=task_id,
        source_platform=platform,
        drama_name=drama_name,
        link_type=link_type,
        promotion_url=promotion_url,
        acquisition_method=method,
        acquisition_status=acquisition_status,
        verification_status=verification_status,
        created_or_existing=CreationStatus.EXISTING,
    )


def _make_task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )


class _FakeProvider:
    """可控模拟 Provider。"""

    def __init__(self, result: AcquisitionResult) -> None:
        self._result = result

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        return AcquisitionResult(
            status=self._result.status,
            expected_types=list(self._result.expected_types),
            candidates=list(self._result.candidates),
            selected=list(self._result.selected),
            missing=dict(self._result.missing),
            diagnostics=dict(self._result.diagnostics),
        )


# ---------------------------------------------------------------------------
# 正常流程：全档位找到 → READY
# ---------------------------------------------------------------------------


def test_pipeline_all_found_ready() -> None:
    """IAA / 2.9 / 9.9 全部找到并验证通过 → READY。"""
    iaa = _make_asset(asset_id="a-iaa", link_type="IAA", promotion_url="mock://iaa")
    a29 = _make_asset(asset_id="a-29", link_type="2.9", promotion_url="mock://29")
    a99 = _make_asset(asset_id="a-99", link_type="9.9", promotion_url="mock://99")

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.COMPLETE,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[iaa, a29, a99],
        selected=[iaa, a29, a99],
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    assert outcome.status == PipelineOutcome.READY
    assert "IAA" in outcome.link_set
    assert "2.9" in outcome.link_set
    assert "9.9" in outcome.link_set
    assert outcome.link_set["2.9"] == "mock://29"


def test_pipeline_partial_found_ready() -> None:
    """只有 2.9 找到 → 部分就绪，非 READY。"""
    a29 = _make_asset(asset_id="a-29", link_type="2.9", promotion_url="mock://29")

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.PARTIAL,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[a29],
        selected=[a29],
        missing={"IAA": "NOT_FOUND", "9.9": "NOT_FOUND"},
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    assert outcome.status != PipelineOutcome.READY
    assert "2.9" in outcome.link_set
    assert "IAA" not in outcome.link_set
    assert outcome.missing.get("IAA") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# AMBIGUOUS → MANUAL_REVIEW
# ---------------------------------------------------------------------------


def test_pipeline_ambiguous_manual_review() -> None:
    """有歧义 → MANUAL_REVIEW。"""
    a1 = _make_asset(asset_id="a1", link_type="2.9", promotion_url="mock://a")
    a2 = _make_asset(asset_id="a2", link_type="2.9", promotion_url="mock://b")

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.AMBIGUOUS,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[a1, a2],
        missing={"2.9": "MULTIPLE_CANDIDATES"},
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    assert outcome.status == PipelineOutcome.MANUAL_REVIEW
    assert "2.9" not in outcome.link_set


# ---------------------------------------------------------------------------
# 全部缺失 → FAILED
# ---------------------------------------------------------------------------


def test_pipeline_all_missing_failed() -> None:
    """全部档位都找不到 → FAILED。"""
    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.NOT_FOUND,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[],
        missing={"IAA": "NOT_FOUND", "2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    assert outcome.status == PipelineOutcome.FAILED
    assert outcome.link_set == {}


# ---------------------------------------------------------------------------
# 验证失败 → MANUAL_REVIEW
# ---------------------------------------------------------------------------


def test_pipeline_validation_failure_manual_review() -> None:
    """资产验证失败 → MANUAL_REVIEW。"""
    # 平台不匹配 → 验证失败
    bad_asset = _make_asset(
        asset_id="bad-1", link_type="2.9",
        platform="WRONG_PLATFORM",
        promotion_url="mock://bad",
    )

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.COMPLETE,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[bad_asset],
        selected=[bad_asset],
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    assert outcome.status == PipelineOutcome.MANUAL_REVIEW
    assert "2.9" not in outcome.link_set


# ---------------------------------------------------------------------------
# link_set 冻结：只含双重验证通过的资产
# ---------------------------------------------------------------------------


def test_pipeline_freezes_only_validated_assets() -> None:
    """link_set 只包含验证通过的资产，验证失败的不冻结。"""
    good = _make_asset(
        asset_id="good", link_type="2.9",
        promotion_url="mock://good",
    )
    # 剧名不匹配 → 验证失败
    bad = _make_asset(
        asset_id="bad", link_type="9.9",
        promotion_url="mock://bad",
        drama_name="别的剧",
    )

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.COMPLETE,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[good, bad],
        selected=[good, bad],
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    # 只有 good 被冻结
    assert "2.9" in outcome.link_set
    assert "9.9" not in outcome.link_set


# ---------------------------------------------------------------------------
# 诊断信息
# ---------------------------------------------------------------------------


def test_pipeline_diagnostics_contains_summary() -> None:
    """诊断信息包含完整摘要。"""
    a29 = _make_asset(asset_id="a-29", link_type="2.9", promotion_url="mock://29")

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.PARTIAL,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[a29],
        selected=[a29],
        missing={"IAA": "NOT_FOUND", "9.9": "NOT_FOUND"},
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    diag = outcome.diagnostics
    assert "acquisition_status" in diag
    assert "validated_count" in diag
    assert "frozen_count" in diag
    assert "missing" in diag


# ---------------------------------------------------------------------------
# per-type 状态明细
# ---------------------------------------------------------------------------


def test_pipeline_per_type_status() -> None:
    """per_type 字段包含每个档位的状态。"""
    iaa = _make_asset(asset_id="a-iaa", link_type="IAA", promotion_url="mock://iaa")
    a29 = _make_asset(asset_id="a-29", link_type="2.9", promotion_url="mock://29")

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.PARTIAL,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[iaa, a29],
        selected=[iaa, a29],
        missing={"9.9": "NOT_FOUND"},
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    per_type = outcome.per_type
    assert per_type.get("IAA") == "FOUND"
    assert per_type.get("2.9") == "FOUND"
    assert per_type.get("9.9") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 空资产 URL 不冻结
# ---------------------------------------------------------------------------


def test_pipeline_empty_url_not_frozen() -> None:
    """URL 为空的资产不进入 link_set。"""
    empty_url_asset = _make_asset(
        asset_id="empty", link_type="2.9",
        promotion_url="",
    )

    provider = _FakeProvider(AcquisitionResult(
        status=AcquisitionStatus.COMPLETE,
        expected_types=["IAA", "2.9", "9.9"],
        candidates=[empty_url_asset],
        selected=[empty_url_asset],
    ))

    pipeline = V2AcquisitionPipeline(provider=provider)
    outcome = pipeline.run(_make_task())

    # URL 为空 → 不冻结
    assert "2.9" not in outcome.link_set

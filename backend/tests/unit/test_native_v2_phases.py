"""DramaResourceService + NativeWorkflowService + Resume + ManualReview + Snapshot 单元测试。

覆盖 Phase 10–15 的核心逻辑。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.acquisition.v2_pipeline import (
    PipelineOutcome,
    PipelineResult,
    V2AcquisitionPipeline,
)
from backend.domain.assets.drama_resource import DramaResource, DramaResourceStatus
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.services.drama_resource_service import (
    DramaResourceService,
    DramaResourceOutcome,
)
from backend.domain.services.manual_review import (
    ManualReviewAction,
    ManualReviewService,
)
from backend.domain.services.native_workflow_service import (
    NativePreparationStatus,
    NativeWorkflowService,
    PreparationStep,
)
from backend.domain.services.resume_service import ResumeService
from backend.domain.services.snapshot_service import (
    NativePreparationSnapshot,
    SnapshotService,
)
from backend.domain.tasks.drama_task import DramaTask, TaskStatus


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _make_task(
    *,
    task_id: str = "task-1",
    drama_name: str = "测试剧",
    status: str = TaskStatus.WAITING_TIME,
    link_set: dict[str, str] | None = None,
) -> DramaTask:
    task = DramaTask(
        id=task_id,
        drama_name=drama_name,
        platform="TOMATO",
        available_time=TARGET_TIME,
        status=status,
    )
    if link_set:
        task.link_set = link_set
    return task


# ===========================================================================
# Phase 10: DramaResourceService
# ===========================================================================


class _FakeAlbumClient:
    """模拟投放系统 album_id 查询客户端。"""

    def __init__(
        self,
        results: dict[str, list[dict]] | None = None,
    ) -> None:
        self._results = results or {}
        self.query_count = 0

    def search(self, drama_name: str) -> list[dict]:
        self.query_count += 1
        return list(self._results.get(drama_name, []))


def test_drama_resource_ensure_album_id_found() -> None:
    """查到唯一 album_id → FOUND。"""
    client = _FakeAlbumClient(results={"测试剧": [
        {"album_id": "album-123", "drama_name": "测试剧"},
    ]})
    service = DramaResourceService(client=client)

    result = service.ensure_album_id(_make_task())

    assert result.outcome == DramaResourceOutcome.FOUND
    assert result.album_id == "album-123"
    assert client.query_count == 1


def test_drama_resource_ensure_album_id_ambiguous() -> None:
    """查到多个结果 → AMBIGUOUS → MANUAL_REVIEW。"""
    client = _FakeAlbumClient(results={"测试剧": [
        {"album_id": "album-1", "drama_name": "测试剧"},
        {"album_id": "album-2", "drama_name": "测试剧"},
    ]})
    service = DramaResourceService(client=client)

    result = service.ensure_album_id(_make_task())

    assert result.outcome == DramaResourceOutcome.AMBIGUOUS
    assert result.album_id is None


def test_drama_resource_ensure_album_id_not_found() -> None:
    """查不到 → NOT_FOUND。"""
    client = _FakeAlbumClient(results={})
    service = DramaResourceService(client=client)

    result = service.ensure_album_id(_make_task())

    assert result.outcome == DramaResourceOutcome.NOT_FOUND
    assert result.album_id is None


def test_drama_resource_reuse_existing() -> None:
    """已有 album_id → 直接复用，不重复查询。"""
    client = _FakeAlbumClient()
    service = DramaResourceService(client=client)
    existing = DramaResource(
        task_id="task-1", drama_name="测试剧",
        album_id="album-existing",
        status=DramaResourceStatus.FOUND.value,
    )

    result = service.ensure_album_id(_make_task(), existing=existing)

    assert result.outcome == DramaResourceOutcome.REUSED
    assert result.album_id == "album-existing"
    assert client.query_count == 0  # 没有查询


# ===========================================================================
# Phase 11: NativeWorkflowService
# ===========================================================================


class _FakeV2Pipeline:
    """模拟 V2 管线。"""

    def __init__(self, result: PipelineResult) -> None:
        self._result = result
        self.call_count = 0

    def run(self, task: DramaTask) -> PipelineResult:
        self.call_count += 1
        return self._result


class _FakeDramaResourceService:
    """模拟 DramaResourceService。"""

    def __init__(self, outcome: DramaResourceOutcome, album_id: str | None = None):
        self._outcome = outcome
        self._album_id = album_id
        self.call_count = 0

    def ensure_album_id(self, task, existing=None):
        self.call_count += 1
        from backend.domain.services.drama_resource_service import DramaResourceResult
        return DramaResourceResult(
            outcome=self._outcome,
            album_id=self._album_id,
            resource=None,
        )


def _make_pipeline_result(
    *,
    status: str = PipelineOutcome.READY,
    link_set: dict[str, str] | None = None,
) -> PipelineResult:
    return PipelineResult(
        status=status,
        link_set=link_set or {"IAA": "mock://iaa", "2.9": "mock://29", "9.9": "mock://99"},
        per_type={"IAA": "FOUND", "2.9": "FOUND", "9.9": "FOUND"},
    )


def test_native_workflow_full_success() -> None:
    """完整成功：剧目确认 → 推广 → album_id → NATIVE_PREPARED。"""
    pipeline = _FakeV2Pipeline(_make_pipeline_result())
    resource_svc = _FakeDramaResourceService(DramaResourceOutcome.FOUND, "album-123")
    workflow = NativeWorkflowService(
        pipeline=pipeline,
        drama_resource_service=resource_svc,
    )

    task = _make_task()
    result = workflow.execute(task)

    assert result.status == NativePreparationStatus.NATIVE_PREPARED
    assert task.link_set.get("2.9") == "mock://29"
    assert task.delivery_drama_id == "album-123"
    assert task.status == "NATIVE_PREPARED"


def test_native_workflow_promotion_failed() -> None:
    """推广链接失败 → MANUAL_REVIEW。"""
    pipeline = _FakeV2Pipeline(PipelineResult(
        status=PipelineOutcome.MANUAL_REVIEW,
        link_set={},
        per_type={"2.9": "AMBIGUOUS"},
    ))
    resource_svc = _FakeDramaResourceService(DramaResourceOutcome.FOUND)
    workflow = NativeWorkflowService(
        pipeline=pipeline,
        drama_resource_service=resource_svc,
    )

    task = _make_task()
    result = workflow.execute(task)

    assert result.status == NativePreparationStatus.MANUAL_REVIEW
    assert task.status == "MANUAL_REVIEW"
    assert resource_svc.call_count == 0  # 推广失败不查 album_id


def test_native_workflow_album_id_ambiguous() -> None:
    """album_id 歧义 → MANUAL_REVIEW。"""
    pipeline = _FakeV2Pipeline(_make_pipeline_result())
    resource_svc = _FakeDramaResourceService(DramaResourceOutcome.AMBIGUOUS)
    workflow = NativeWorkflowService(
        pipeline=pipeline,
        drama_resource_service=resource_svc,
    )

    task = _make_task()
    result = workflow.execute(task)

    assert result.status == NativePreparationStatus.MANUAL_REVIEW
    assert result.failed_step == PreparationStep.ENSURE_ALBUM_ID


# ===========================================================================
# Phase 12: Resume + Idempotency
# ===========================================================================


def test_resume_skips_completed_steps() -> None:
    """Resume 跳过已完成的步骤。"""
    pipeline = _FakeV2Pipeline(_make_pipeline_result())
    resource_svc = _FakeDramaResourceService(DramaResourceOutcome.FOUND, "album-123")
    workflow = NativeWorkflowService(
        pipeline=pipeline,
        drama_resource_service=resource_svc,
    )

    # 已经有 link_set 和 delivery_drama_id
    task = _make_task(
        link_set={"IAA": "mock://iaa", "2.9": "mock://29", "9.9": "mock://99"},
    )
    task.delivery_drama_id = "album-123"
    task.current_stage = "ALBUM_READY"

    result = workflow.execute(task)

    assert result.status == NativePreparationStatus.NATIVE_PREPARED
    assert pipeline.call_count == 0  # 推广已完成，不重复
    assert resource_svc.call_count == 0  # album_id 已有，不重复


def test_resume_from_partial() -> None:
    """部分完成时从断点继续。"""
    pipeline = _FakeV2Pipeline(_make_pipeline_result())
    resource_svc = _FakeDramaResourceService(DramaResourceOutcome.FOUND, "album-123")
    workflow = NativeWorkflowService(
        pipeline=pipeline,
        drama_resource_service=resource_svc,
    )

    # 推广已完成但没有 album_id
    task = _make_task(
        link_set={"IAA": "mock://iaa", "2.9": "mock://29", "9.9": "mock://99"},
    )
    task.current_stage = "PROMOTION_READY"

    result = workflow.execute(task)

    assert result.status == NativePreparationStatus.NATIVE_PREPARED
    assert pipeline.call_count == 0  # 推广已完成
    assert resource_svc.call_count == 1  # 需要查 album_id


# ===========================================================================
# Phase 14: Manual Review
# ===========================================================================


def test_manual_review_resolve_and_resume() -> None:
    """人工确认后继续执行。"""
    review_service = ManualReviewService()
    task = _make_task(status=TaskStatus.MANUAL_REVIEW)
    task.current_stage = "PROMOTION_READY"

    action = ManualReviewAction(
        task_id="task-1",
        resolution="confirm_ambiguous",
        data={"selected_promotion_id": "promo-correct"},
    )

    result = review_service.resolve(task, action)

    assert result.is_resolved is True
    assert task.status == TaskStatus.WAITING_TIME  # 回到待执行


def test_manual_review_reject_stays() -> None:
    """拒绝确认 → 保持 MANUAL_REVIEW。"""
    review_service = ManualReviewService()
    task = _make_task(status=TaskStatus.MANUAL_REVIEW)

    action = ManualReviewAction(
        task_id="task-1",
        resolution="reject",
        data={},
    )

    result = review_service.resolve(task, action)

    assert result.is_resolved is False
    assert task.status == TaskStatus.MANUAL_REVIEW


# ===========================================================================
# Phase 15: NativePreparationSnapshot
# ===========================================================================


def test_snapshot_generation() -> None:
    """生成冻结快照。"""
    task = _make_task()
    task.link_set = {"IAA": "mock://iaa", "2.9": "mock://29", "9.9": "mock://99"}
    task.delivery_drama_id = "album-123"
    task.status = "NATIVE_PREPARED"

    pipeline_result = _make_pipeline_result()
    snapshot = SnapshotService.generate(task, pipeline_result)

    assert snapshot.task_id == "task-1"
    assert snapshot.drama_name == "测试剧"
    assert snapshot.link_set == task.link_set
    assert snapshot.album_id == "album-123"
    assert snapshot.status == "NATIVE_PREPARED"
    assert snapshot.prepared_at is not None


def test_snapshot_freezes_all_data() -> None:
    """快照冻结所有关键数据，后续只读。"""
    task = _make_task()
    task.link_set = {"2.9": "mock://29"}
    task.delivery_drama_id = "album-456"

    snapshot = SnapshotService.generate(task, _make_pipeline_result())

    # 快照是独立副本，修改原 task 不影响快照
    task.link_set["2.9"] = "changed"
    assert snapshot.link_set["2.9"] == "mock://29"

    d = snapshot.to_dict()
    assert d["task_id"] == "task-1"
    assert d["album_id"] == "album-456"
    assert "prepared_at" in d

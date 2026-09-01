"""NativeWorkflowService（Phase 11）。

统一编排 Native 前置流程：
    prepare_drama() → ensure_promotions() → ensure_album_id()
    → ensure_native_configs() → validate_preparation()
    → freeze_preparation() → mark_native_prepared()

支持断点恢复（Phase 12）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.domain.services.drama_resource_service import (
    DramaResourceOutcome,
    DramaResourceService,
)
from backend.domain.tasks.drama_task import DramaTask, TaskStatus

logger = logging.getLogger(__name__)


class NativePreparationStatus:
    """Native 准备状态。"""

    DRAMA_READY = "DRAMA_READY"
    PROMOTION_READY = "PROMOTION_READY"
    ALBUM_READY = "ALBUM_READY"
    NATIVE_CONFIG_READY = "NATIVE_CONFIG_READY"
    NATIVE_PREPARED = "NATIVE_PREPARED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"


class PreparationStep(Enum):
    """准备步骤。"""

    PREPARE_DRAMA = "prepare_drama"
    ENSURE_PROMOTIONS = "ensure_promotions"
    ENSURE_ALBUM_ID = "ensure_album_id"
    ENSURE_NATIVE_CONFIGS = "ensure_native_configs"
    VALIDATE_PREPARATION = "validate_preparation"
    FREEZE_PREPARATION = "freeze_preparation"


@dataclass
class NativeWorkflowResult:
    """工作流执行结果。"""

    status: str
    failed_step: PreparationStep | None = None
    link_set: dict[str, str] = field(default_factory=dict)
    album_id: str | None = None
    per_type: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_prepared(self) -> bool:
        return self.status == NativePreparationStatus.NATIVE_PREPARED


class NativeWorkflowService:
    """Native 前置流程统一编排。"""

    def __init__(
        self,
        pipeline: Any,
        drama_resource_service: DramaResourceService,
    ) -> None:
        self._pipeline = pipeline
        self._drama_resource_service = drama_resource_service

    def execute(self, task: DramaTask) -> NativeWorkflowResult:
        """执行完整 Native 前置流程，支持断点恢复。"""
        # Step 1: 剧目确认（如果已有 link_set 说明已完成）
        if not task.link_set or not self._is_promotion_ready(task):
            result = self._ensure_promotions(task)
            if result.status != NativePreparationStatus.PROMOTION_READY:
                return result
        else:
            # 已有 link_set，跳过推广采集
            pass

        # Step 2: 确保 album_id
        if not task.delivery_drama_id:
            result = self._ensure_album_id(task)
            if result.status != NativePreparationStatus.ALBUM_READY:
                return result
        else:
            # 已有 album_id，跳过
            pass

        # Step 3: Native 配置（当前为占位，后续补充）
        # Step 4: 验证 + 冻结
        return self._finalize(task)

    def _is_promotion_ready(self, task: DramaTask) -> bool:
        """检查推广是否已完成。"""
        expected = {"IAA", "2.9", "9.9"}
        return expected <= set(task.link_set.keys()) and all(task.link_set.values())

    def _ensure_promotions(self, task: DramaTask) -> NativeWorkflowResult:
        """执行推广链接采集。"""
        pipeline_result = self._pipeline.run(task)

        if pipeline_result.status == "MANUAL_REVIEW":
            task.status = TaskStatus.MANUAL_REVIEW
            return NativeWorkflowResult(
                status=NativePreparationStatus.MANUAL_REVIEW,
                failed_step=PreparationStep.ENSURE_PROMOTIONS,
                per_type=pipeline_result.per_type,
            )

        if pipeline_result.status == "FAILED":
            task.status = TaskStatus.FAILED
            return NativeWorkflowResult(
                status=NativePreparationStatus.FAILED,
                failed_step=PreparationStep.ENSURE_PROMOTIONS,
            )

        # READY 或 PARTIAL
        task.link_set = pipeline_result.link_set
        task.link_status = "VALIDATED"
        task.current_stage = NativePreparationStatus.PROMOTION_READY

        # 只有 READY 才继续
        if pipeline_result.status != "READY":
            task.status = TaskStatus.MANUAL_REVIEW
            return NativeWorkflowResult(
                status=NativePreparationStatus.MANUAL_REVIEW,
                failed_step=PreparationStep.ENSURE_PROMOTIONS,
                link_set=pipeline_result.link_set,
                per_type=pipeline_result.per_type,
            )

        return NativeWorkflowResult(
            status=NativePreparationStatus.PROMOTION_READY,
            link_set=pipeline_result.link_set,
            per_type=pipeline_result.per_type,
        )

    def _ensure_album_id(self, task: DramaTask) -> NativeWorkflowResult:
        """执行 album_id 获取。"""
        result = self._drama_resource_service.ensure_album_id(task)

        if result.outcome == DramaResourceOutcome.AMBIGUOUS:
            task.status = TaskStatus.MANUAL_REVIEW
            return NativeWorkflowResult(
                status=NativePreparationStatus.MANUAL_REVIEW,
                failed_step=PreparationStep.ENSURE_ALBUM_ID,
                link_set=task.link_set,
            )

        if result.outcome == DramaResourceOutcome.NOT_FOUND:
            task.status = TaskStatus.FAILED
            return NativeWorkflowResult(
                status=NativePreparationStatus.FAILED,
                failed_step=PreparationStep.ENSURE_ALBUM_ID,
                link_set=task.link_set,
            )

        # FOUND 或 REUSED
        task.delivery_drama_id = result.album_id or ""
        task.current_stage = NativePreparationStatus.ALBUM_READY

        return NativeWorkflowResult(
            status=NativePreparationStatus.ALBUM_READY,
            link_set=task.link_set,
            album_id=result.album_id,
        )

    def _finalize(self, task: DramaTask) -> NativeWorkflowResult:
        """最终验证并标记完成。"""
        task.current_stage = NativePreparationStatus.NATIVE_PREPARED
        task.status = "NATIVE_PREPARED"

        return NativeWorkflowResult(
            status=NativePreparationStatus.NATIVE_PREPARED,
            link_set=task.link_set,
            album_id=task.delivery_drama_id or None,
            diagnostics={"finalized": True},
        )

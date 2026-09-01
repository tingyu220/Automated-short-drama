"""ResumeService（Phase 12）。

断点恢复：检查已完成的步骤，只执行未完成的部分。
所有有副作用的操作统一用 ensure_xxx() 语义。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.domain.services.native_workflow_service import (
    NativePreparationStatus,
    NativeWorkflowService,
)
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


@dataclass
class ResumeResult:
    """Resume 执行结果。"""

    resumed_from: str
    status: str
    skipped_steps: list[str]


class ResumeService:
    """断点恢复服务。

    检查任务当前阶段，确定从哪个步骤继续执行。
    """

    STAGE_ORDER = [
        NativePreparationStatus.DRAMA_READY,
        NativePreparationStatus.PROMOTION_READY,
        NativePreparationStatus.ALBUM_READY,
        NativePreparationStatus.NATIVE_CONFIG_READY,
        NativePreparationStatus.NATIVE_PREPARED,
    ]

    def __init__(self, workflow: NativeWorkflowService) -> None:
        self._workflow = workflow

    def resume(self, task: DramaTask) -> ResumeResult:
        """从断点恢复执行。"""
        current = task.current_stage
        skipped = self._completed_steps(current)

        result = self._workflow.execute(task)

        return ResumeResult(
            resumed_from=current,
            status=result.status,
            skipped_steps=skipped,
        )

    def _completed_steps(self, current_stage: str) -> list[str]:
        """返回已完成的步骤列表。"""
        if current_stage not in self.STAGE_ORDER:
            return []
        idx = self.STAGE_ORDER.index(current_stage)
        return self.STAGE_ORDER[:idx + 1]

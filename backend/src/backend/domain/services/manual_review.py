"""ManualReviewService（Phase 14）。

只允许真正无法自动判断的问题进入人工。
人工确认后保存结果 → Resume，不重新执行整个任务。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.domain.tasks.drama_task import DramaTask, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class ManualReviewAction:
    """人工审核动作。"""

    task_id: str
    resolution: str  # confirm_ambiguous / reject / select_candidate
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManualReviewResult:
    """人工审核结果。"""

    is_resolved: bool
    task_id: str
    message: str = ""


class ManualReviewService:
    """人工审核服务。"""

    def resolve(
        self,
        task: DramaTask,
        action: ManualReviewAction,
    ) -> ManualReviewResult:
        """处理人工审核动作。"""
        if action.resolution == "reject":
            return ManualReviewResult(
                is_resolved=False,
                task_id=task.id,
                message="manual review rejected",
            )

        # 确认后回到待执行状态，等待 Resume
        task.status = TaskStatus.WAITING_TIME
        return ManualReviewResult(
            is_resolved=True,
            task_id=task.id,
            message=f"resolved with {action.resolution}",
        )

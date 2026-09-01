"""SnapshotService + NativePreparationSnapshot（Phase 15）。

进入 NATIVE_PREPARED 前必须生成冻结快照。
这是后续自动上计划唯一允许消费的输入。
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.domain.acquisition.v2_pipeline import PipelineResult
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


@dataclass
class NativePreparationSnapshot:
    """Native 准备冻结快照。

    包含所有已验证的数据，后续 Auto Plan 只读此快照。
    """

    task_id: str
    drama_name: str
    external_drama_id: str | None = None
    link_set: dict[str, str] = field(default_factory=dict)
    album_id: str | None = None
    per_type: dict[str, str] = field(default_factory=dict)
    status: str = ""
    prepared_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "drama_name": self.drama_name,
            "external_drama_id": self.external_drama_id,
            "link_set": dict(self.link_set),
            "album_id": self.album_id,
            "per_type": dict(self.per_type),
            "status": self.status,
            "prepared_at": self.prepared_at.isoformat(),
        }


class SnapshotService:
    """生成 Native 准备快照。"""

    @staticmethod
    def generate(
        task: DramaTask,
        pipeline_result: PipelineResult,
    ) -> NativePreparationSnapshot:
        """从任务和管线结果生成冻结快照。"""
        return NativePreparationSnapshot(
            task_id=task.id,
            drama_name=task.drama_name,
            external_drama_id=task.confirmed_drama_match.locator_key
            if task.confirmed_drama_match
            else None,
            link_set=copy.deepcopy(dict(task.link_set)),
            album_id=task.delivery_drama_id or None,
            per_type=copy.deepcopy(dict(pipeline_result.per_type)),
            status=task.status,
        )

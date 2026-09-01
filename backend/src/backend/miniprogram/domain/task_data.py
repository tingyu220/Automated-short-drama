"""MiniProgram 任务数据领域实体。

业务数据与 Native 完全隔离，不写入 NativePromotionAsset 或 link_set。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.miniprogram.domain.workflow_state import MiniProgramWorkflowStatus


@dataclass
class MiniProgramTaskData:
    """MiniProgram 任务持久化数据。"""

    task_id: str
    drama_name: str
    operator_name: str
    operator_code: str
    organization_group: str
    organization_path: str
    drama_short_name: str | None = None
    album_id: str | None = None
    workflow_status: str = MiniProgramWorkflowStatus.NOT_STARTED
    id: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def touch(self) -> None:
        """更新 updated_at 时间戳。"""
        self.updated_at = datetime.now(timezone.utc)

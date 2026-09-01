"""DramaResource 领域模型（Phase 10）。

独立管理 album_id，供 Native 和 MiniProgram 复用。

流程：
    已有 → Reuse
    没有 → Query
    唯一结果 → Save
    多个结果 → MANUAL_REVIEW
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class DramaResourceStatus(Enum):
    """DramaResource 状态。"""

    NOT_QUERIED = "NOT_QUERIED"
    FOUND = "FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


@dataclass
class DramaResource:
    """剧目资源资产（album_id 独立化）。

    保存剧名、external_drama_id、album_id 等，
    供后续商品、落地页等直接复用，不重复查询。
    """

    task_id: str
    drama_name: str
    external_drama_id: str | None = None
    album_id: str | None = None
    status: str = DramaResourceStatus.NOT_QUERIED.value
    queried_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    candidates: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == DramaResourceStatus.FOUND.value and bool(self.album_id)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "drama_name": self.drama_name,
            "external_drama_id": self.external_drama_id,
            "album_id": self.album_id,
            "status": self.status,
            "queried_at": self.queried_at.isoformat() if self.queried_at else None,
            "error": self.error,
        }

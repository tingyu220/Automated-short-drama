"""DramaResourceService（Phase 10）。

独立管理 album_id，供 Native 和 MiniProgram 复用。

流程：
    已有 → Reuse
    没有 → Query
    唯一结果 → Save
    多个结果 → AMBIGUOUS → MANUAL_REVIEW
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from backend.domain.assets.drama_resource import (
    DramaResource,
    DramaResourceStatus,
)
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


class DramaResourceOutcome(Enum):
    REUSED = "REUSED"
    FOUND = "FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


@dataclass
class DramaResourceResult:
    outcome: DramaResourceOutcome
    album_id: str | None = None
    resource: DramaResource | None = None


class AlbumClient(Protocol):
    """投放系统 album_id 查询客户端协议。"""

    def search(self, drama_name: str) -> list[dict]: ...


class DramaResourceService:
    """album_id 获取与复用服务。"""

    def __init__(
        self,
        client: AlbumClient,
    ) -> None:
        self._client = client

    def ensure_album_id(
        self,
        task: DramaTask,
        *,
        existing: DramaResource | None = None,
    ) -> DramaResourceResult:
        """确保 album_id 存在，有则复用，无则查询。"""
        if existing and existing.is_ready:
            return DramaResourceResult(
                outcome=DramaResourceOutcome.REUSED,
                album_id=existing.album_id,
                resource=existing,
            )

        resource = existing or DramaResource(
            task_id=task.id,
            drama_name=task.drama_name,
        )

        results = self._client.search(task.drama_name)

        if len(results) == 0:
            resource.status = DramaResourceStatus.NOT_FOUND.value
            return DramaResourceResult(
                outcome=DramaResourceOutcome.NOT_FOUND,
                resource=resource,
            )

        if len(results) > 1:
            resource.status = DramaResourceStatus.AMBIGUOUS.value
            resource.candidates = results
            return DramaResourceResult(
                outcome=DramaResourceOutcome.AMBIGUOUS,
                resource=resource,
            )

        album_id = results[0].get("album_id", "")
        resource.album_id = album_id
        resource.external_drama_id = results[0].get("external_drama_id")
        resource.status = DramaResourceStatus.FOUND.value
        from datetime import datetime, timezone
        resource.queried_at = datetime.now(timezone.utc)

        return DramaResourceResult(
            outcome=DramaResourceOutcome.FOUND,
            album_id=album_id,
            resource=resource,
        )

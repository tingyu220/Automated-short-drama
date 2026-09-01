"""SimpleDomFallback（Phase 13）。

DOM 从主路径降级为最后兜底。
包装 LegacyDomProvider，只在没有 API/Network 结果时使用。
"""
from __future__ import annotations

import logging

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


class SimpleDomFallback:
    """DOM 兜底 Provider。

    只作为 FallbackChain 的最后一个 Provider。
    标记为 DOM 方法，不做复杂逻辑。
    """

    def __init__(self, legacy_provider) -> None:
        self._legacy = legacy_provider

    @property
    def name(self) -> str:
        return "DOM"

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """DOM 兜底采集。"""
        logger.info("DOM fallback triggered for task %s", task.id)
        result = self._legacy.acquire(task)
        result.diagnostics["dom_fallback"] = True
        return result

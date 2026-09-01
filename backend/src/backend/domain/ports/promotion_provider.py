"""推广资产采集 Provider 协议。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.domain.acquisition.acquisition_result import AcquisitionResult
from backend.domain.tasks.drama_task import DramaTask


@runtime_checkable
class PromotionProvider(Protocol):
    """平台内部的一种推广资产获取方式。"""

    def acquire(self, task: DramaTask) -> AcquisitionResult: ...


"""Shadow Mode Provider（Phase 7）。

包装 Legacy DOM Provider 和 Network V2 Provider，
支持三种运行模式：

- LEGACY: 只用 Legacy DOM（当前生产模式）
- SHADOW: Legacy 走生产 + Network 只观察对比
- V2: 只用 Network（未来生产模式）

SHADOW 模式下返回 Legacy 结果作为生产结果，
同时在 diagnostics 中附加 shadow_comparison 对比信息。
"""
from __future__ import annotations

import logging
from enum import Enum

from backend.domain.acquisition.acquisition_result import AcquisitionResult
from backend.domain.acquisition.shadow_comparator import ShadowComparator
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)


class ShadowMode(Enum):
    """Shadow 运行模式。"""

    LEGACY = "LEGACY"
    SHADOW = "SHADOW"
    V2 = "V2"


class ShadowModeProvider:
    """根据运行模式分发到 Legacy 或 Network Provider。

    实现 PromotionProvider 协议（acquire 方法）。
    """

    def __init__(
        self,
        legacy,
        network,
        mode: ShadowMode = ShadowMode.LEGACY,
        *,
        comparator: ShadowComparator | None = None,
    ) -> None:
        self._legacy = legacy
        self._network = network
        self._mode = mode
        self._comparator = comparator or ShadowComparator()

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """根据运行模式执行采集。"""
        if self._mode == ShadowMode.LEGACY:
            return self._run_legacy(task)
        if self._mode == ShadowMode.V2:
            return self._run_v2(task)
        return self._run_shadow(task)

    def _run_legacy(self, task: DramaTask) -> AcquisitionResult:
        """LEGACY 模式：只用 Legacy DOM。"""
        result = self._legacy.acquire(task)
        result.diagnostics["shadow_mode"] = "LEGACY"
        return result

    def _run_v2(self, task: DramaTask) -> AcquisitionResult:
        """V2 模式：只用 Network Provider。"""
        result = self._network.acquire(task)
        result.diagnostics["shadow_mode"] = "V2"
        return result

    def _run_shadow(self, task: DramaTask) -> AcquisitionResult:
        """SHADOW 模式：Legacy 走生产，Network 只观察。"""
        legacy_result = self._legacy.acquire(task)
        v2_result = self._network.acquire(task)

        comparison = self._comparator.compare(legacy_result, v2_result)

        # 生产结果用 Legacy 的
        legacy_result.diagnostics["shadow_mode"] = "SHADOW"
        legacy_result.diagnostics["shadow_comparison"] = comparison.to_dict()

        return legacy_result

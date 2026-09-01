"""Scoped Network Provider：编排 DOM 搜索 → Network 确认。

优化流程（减少不必要的调用）：
1. begin_scope(task_id) — 清除上一轮 captures
2. DOM 搜索 + 创建（LegacyDomProvider）— 触发网络响应
3. 如果 DOM 全部找到且无需创建 → 快速返回（跳过 Network 确认）
4. 如果 DOM 有缺失或创建了新链接 → Network 读取 captures 确认
5. 合并结果：Network 优先，补充 DOM
6. 仍缺失 → RESULT_UNCERTAIN
7. end_scope()
"""
from __future__ import annotations

import logging
from typing import Any

from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import PromotionAsset
from backend.domain.tasks.drama_task import DramaTask

logger = logging.getLogger(__name__)

_ALL_EXPECTED = {"IAA", "2.9", "9.9"}


class ScopedNetworkProvider:
    """编排 DOM 搜索 + Network 确认的 Provider。"""

    def __init__(
        self,
        *,
        listener: Any,
        network_provider: Any,
        legacy_provider: Any,
    ) -> None:
        self._listener = listener
        self._network = network_provider
        self._legacy = legacy_provider

    @property
    def name(self) -> str:
        return "SCOPED_NETWORK"

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        """执行 DOM 搜索 → Network 确认流程。"""
        self._listener.begin_scope(task.id)

        # Phase 1: DOM 搜索 + 创建（触发网络响应）
        dom_result = self._legacy.acquire(task)
        dom_types = {a.link_type for a in dom_result.selected}

        # 快速路径：DOM 全部找到且无创建操作 → 直接返回
        dom_created = any(
            getattr(a, "created_or_existing", "") == "CREATED"
            for a in dom_result.selected
        )
        if dom_types >= _ALL_EXPECTED and not dom_created:
            self._listener.end_scope()
            return self._annotate(dom_result, "dom_complete_no_create")

        # Phase 2: Network 读取 captures 确认
        logger.info(
            "ScopedNetwork: DOM %s (found=%s, created=%s), triggering Network confirm",
            dom_result.status,
            dom_types,
            dom_created,
        )
        network_result = self._network.acquire(task)

        # Phase 3: 合并 — Network 优先，补充 DOM
        merged = self._merge_results(dom_result, network_result)

        self._listener.end_scope()

        if {a.link_type for a in merged.selected} >= _ALL_EXPECTED:
            return self._annotate(merged, "network_confirmed")

        return self._annotate(merged, "RESULT_UNCERTAIN")

    def _merge_results(
        self,
        dom: AcquisitionResult,
        network: AcquisitionResult,
    ) -> AcquisitionResult:
        """合并结果：Network 优先，补充 DOM。"""
        selected: list[PromotionAsset] = []
        seen_types: set[str] = set()

        for asset in network.selected:
            if asset.link_type not in seen_types:
                selected.append(asset)
                seen_types.add(asset.link_type)

        for asset in dom.selected:
            if asset.link_type not in seen_types:
                selected.append(asset)
                seen_types.add(asset.link_type)

        all_candidates: list[PromotionAsset] = []
        seen_ids: set[str] = set()
        for source in (network, dom):
            for asset in source.candidates:
                if asset.id not in seen_ids:
                    all_candidates.append(asset)
                    seen_ids.add(asset.id)

        missing: dict[str, str] = {}
        for lt in _ALL_EXPECTED:
            if lt not in seen_types:
                missing[lt] = "NOT_FOUND"

        if not missing:
            status = AcquisitionStatus.COMPLETE
        elif selected:
            status = AcquisitionStatus.PARTIAL
        else:
            status = AcquisitionStatus.NOT_FOUND

        return AcquisitionResult(
            status=status,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=all_candidates,
            selected=selected,
            missing=missing,
            warnings=list(dom.warnings) + list(network.warnings),
            diagnostics={
                "scoped_provider": {
                    "dom_status": dom.status,
                    "network_status": network.status,
                    "final_selected_types": sorted(seen_types),
                }
            },
        )

    def _annotate(self, result: AcquisitionResult, final_status: str) -> AcquisitionResult:
        """在 diagnostics 中标注最终状态。"""
        diag = dict(result.diagnostics)
        scoped = diag.get("scoped_provider", {})
        scoped["final_status"] = final_status
        diag["scoped_provider"] = scoped
        return AcquisitionResult(
            status=result.status,
            expected_types=result.expected_types,
            candidates=result.candidates,
            selected=result.selected,
            missing=result.missing,
            warnings=result.warnings,
            diagnostics=diag,
        )

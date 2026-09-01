"""优选平台 MiniProgram Network Discovery Provider（M0-6）。

本阶段只做网络数据发现，不执行任何真实创建。
人工操作页面 + 程序监听 Network Response，记录脱敏后的接口数据。

使用方式：
1. 提供 Playwright page 对象
2. 调用 start_listening() 开始监听
3. 人工在页面上操作（搜索剧目、查看推广等）
4. 调用 stop_and_collect() 获取结果并保存到 artifacts

安全要求：
- 只读，不做任何点击/提交
- 所有数据经过脱敏
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.miniprogram.platforms.youxuan.network.discovery_storage import (
    save_captures_to_artifacts,
)
from backend.miniprogram.platforms.youxuan.network.network_listener import (
    NetworkCaptureRecord,
    YouxuanNetworkListener,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryOutcome:
    """Discovery 执行结果。"""

    status: str  # SUCCESS / NO_DATA / NOT_STARTED
    capture_count: int = 0
    endpoint_types: list[str] = field(default_factory=list)
    endpoint_counts: dict[str, int] = field(default_factory=dict)
    captures: list[NetworkCaptureRecord] = field(default_factory=list)
    artifacts_path: str | None = None
    note: str = ""


class YouxuanNetworkDiscoveryProvider:
    """优选 MiniProgram Network Discovery Provider。

    M0 阶段：纯观察，不操作页面，不创建任何资产。
    """

    def __init__(
        self,
        page: Any = None,
        *,
        platform_domain_keyword: str = "youxuan",
        artifacts_root: str | Path | None = None,
    ) -> None:
        self._page = page
        self._domain_keyword = platform_domain_keyword
        self._artifacts_root = artifacts_root
        self._listener: YouxuanNetworkListener | None = None

    def start_listening(self) -> None:
        """开始监听网络响应。"""
        if self._page is None:
            logger.warning("page 为 None，Network Discovery 未启动")
            return
        if self._listener is not None:
            logger.warning("Network Discovery 已经在运行中")
            return
        self._listener = YouxuanNetworkListener(
            self._page,
            platform_domain_keyword=self._domain_keyword,
        )

    def stop_and_collect(
        self,
        task_id: str | None = None,
        *,
        save_artifacts: bool = True,
    ) -> DiscoveryOutcome:
        """停止监听并收集结果。

        Args:
            task_id: 任务 ID，用于 artifacts 路径
            save_artifacts: 是否保存到 artifacts 目录

        Returns:
            DiscoveryOutcome
        """
        if self._listener is None:
            return DiscoveryOutcome(
                status="NOT_STARTED",
                note="未启动网络监听",
            )

        self._listener.stop()
        captures = self._listener.captures
        summary = self._listener.summary()
        self._listener = None

        if not captures:
            return DiscoveryOutcome(
                status="NO_DATA",
                note="未捕获到任何业务接口响应",
            )

        artifacts_path: str | None = None
        if save_artifacts and task_id:
            try:
                saved_dir = save_captures_to_artifacts(
                    captures,
                    task_id,
                    artifacts_root=self._artifacts_root,
                )
                artifacts_path = str(saved_dir)
            except Exception:
                logger.exception("保存 Discovery artifacts 失败")

        return DiscoveryOutcome(
            status="SUCCESS",
            capture_count=summary["capture_count"],
            endpoint_types=summary["endpoint_types"],
            endpoint_counts=summary["endpoint_counts"],
            captures=captures,
            artifacts_path=artifacts_path,
        )

    @property
    def is_listening(self) -> bool:
        """是否正在监听。"""
        return self._listener is not None

    def current_summary(self) -> dict:
        """当前已捕获的摘要（不停止监听）。"""
        if self._listener is None:
            return {"capture_count": 0, "endpoint_types": [], "listener_attached": False}
        summary = self._listener.summary()
        summary["listener_attached"] = True
        return summary

"""MiniProgram 仓储端口协议。

业务数据与 Native 完全隔离：
- 不读写 NativePromotionAsset
- 不读写 Native link_set
- 不修改 Native Workflow 状态

唯一允许共享的业务数据：album_id。
"""
from __future__ import annotations

from typing import Protocol

from backend.miniprogram.domain.task_data import MiniProgramTaskData


class MiniProgramTaskRepository(Protocol):
    """MiniProgram 任务数据仓储协议。"""

    def save(self, task_data: MiniProgramTaskData) -> MiniProgramTaskData: ...
    def get_by_task_id(self, task_id: str) -> MiniProgramTaskData | None: ...
    def list_all(self) -> list[MiniProgramTaskData]: ...
    def update_status(
        self, task_id: str, status: str
    ) -> MiniProgramTaskData | None: ...
    def delete(self, task_id: str) -> bool: ...

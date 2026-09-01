"""MiniProgram 工作流状态。

M0 只定义到 READY_FOR_IMPLEMENTATION。
后续阶段（PROMOTION_READY / PRODUCT_READY / MINIAPP_READY）在 M1 引入。
"""
from __future__ import annotations


class MiniProgramWorkflowStatus:
    """MiniProgram 工作流状态枚举。"""

    NOT_STARTED = "NOT_STARTED"
    CONTEXT_READY = "CONTEXT_READY"
    DISCOVERY_READY = "DISCOVERY_READY"
    READY_FOR_IMPLEMENTATION = "READY_FOR_IMPLEMENTATION"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"


# 状态流转顺序，用于判断进度
_STATUS_ORDER = [
    MiniProgramWorkflowStatus.NOT_STARTED,
    MiniProgramWorkflowStatus.CONTEXT_READY,
    MiniProgramWorkflowStatus.DISCOVERY_READY,
    MiniProgramWorkflowStatus.READY_FOR_IMPLEMENTATION,
    MiniProgramWorkflowStatus.MANUAL_REVIEW,
    MiniProgramWorkflowStatus.FAILED,
]


def status_rank(status: str) -> int:
    """返回状态在流程中的位置，用于比较进度。"""
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return -1


def is_terminal(status: str) -> bool:
    """是否终态。"""
    return status in (
        MiniProgramWorkflowStatus.READY_FOR_IMPLEMENTATION,
        MiniProgramWorkflowStatus.FAILED,
    )

"""Native 状态机（Phase 12）。

顶层状态：
    WAITING_AVAILABLE_TIME
    ↓
    DRAMA_READY
    ↓
    PROMOTION_READY
    ↓
    ALBUM_READY
    ↓
    NATIVE_CONFIG_READY
    ↓
    NATIVE_PREPARED

异常状态：
    MANUAL_REVIEW
    FAILED
"""
from __future__ import annotations


class NativeStage:
    """Native 准备阶段。"""

    WAITING_AVAILABLE_TIME = "WAITING_AVAILABLE_TIME"
    DRAMA_READY = "DRAMA_READY"
    PROMOTION_READY = "PROMOTION_READY"
    ALBUM_READY = "ALBUM_READY"
    NATIVE_CONFIG_READY = "NATIVE_CONFIG_READY"
    NATIVE_PREPARED = "NATIVE_PREPARED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    FAILED = "FAILED"

    ORDER = (
        WAITING_AVAILABLE_TIME,
        DRAMA_READY,
        PROMOTION_READY,
        ALBUM_READY,
        NATIVE_CONFIG_READY,
        NATIVE_PREPARED,
    )

    TERMINAL_SUCCESS = frozenset({NATIVE_PREPARED})
    TERMINAL_ERROR = frozenset({MANUAL_REVIEW, FAILED})

    @classmethod
    def next_stage(cls, current: str) -> str | None:
        """获取下一个阶段。"""
        try:
            idx = cls.ORDER.index(current)
        except ValueError:
            return None
        if idx + 1 >= len(cls.ORDER):
            return None
        return cls.ORDER[idx + 1]

    @classmethod
    def is_terminal(cls, stage: str) -> bool:
        return stage in cls.TERMINAL_SUCCESS or stage in cls.TERMINAL_ERROR

    @classmethod
    def is_success(cls, stage: str) -> bool:
        return stage in cls.TERMINAL_SUCCESS

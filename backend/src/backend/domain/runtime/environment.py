"""运行环境状态。"""
from __future__ import annotations

from dataclasses import dataclass


class RuntimeMode:
    """自动化适配器运行模式。"""

    MOCK = "MOCK"
    REAL = "REAL"

    @classmethod
    def validate(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {cls.MOCK, cls.REAL}:
            raise ValueError(f"不支持的运行环境: {value}")
        return normalized


@dataclass(frozen=True)
class RuntimeEnvironment:
    """用户目标模式与 Worker 已应用模式。"""

    desired_mode: str = RuntimeMode.MOCK
    worker_mode: str | None = None
    configured: bool = False
    operator_match_group: bool = False

    @property
    def switching(self) -> bool:
        return self.configured and self.worker_mode != self.desired_mode

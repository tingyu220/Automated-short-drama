"""产线端类型常量."""
from __future__ import annotations


class EndType:
    """区分端原生漫剧与微信小程序产线."""

    NATIVE = "NATIVE"
    MINIPROGRAM = "MINIPROGRAM"

    ALL = frozenset({NATIVE, MINIPROGRAM})

    @classmethod
    def validate(cls, value: str) -> str:
        if value not in cls.ALL:
            raise ValueError(f"不支持的端类型: {value}")
        return value

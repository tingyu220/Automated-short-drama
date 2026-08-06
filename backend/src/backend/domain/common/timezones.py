"""统一时区常量与 UTC 归一化工具。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SHANGHAI_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc


def as_utc(value: datetime) -> datetime:
    """将 naive 值视为 UTC，aware 值转换到 UTC。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

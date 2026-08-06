"""平台资源配置领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PlatformResourceConfig:
    """平台通用资源配置领域模型."""

    platform: str
    key: str
    value_json: dict
    enabled: bool = True
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

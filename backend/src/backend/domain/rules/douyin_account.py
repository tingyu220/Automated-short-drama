"""抖音账号领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DouyinAccount:
    """抖音账号领域模型."""

    douyin_account_id: str
    name: str
    status: str
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

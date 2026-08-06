"""投放预设映射领域模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PresetMapping:
    """CID 与广告预设/账户预设映射领域模型."""

    subject: str
    delivery_type: str
    cid: str
    ad_preset: str
    douyin_account: str
    account_open_preset: str
    effective_from: datetime
    enabled: bool = True
    id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

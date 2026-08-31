"""人工确认的番茄剧目候选。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConfirmedDramaMatch:
    """一次人工确认所允许复用的稳定候选定位。"""

    locator_key: str
    available_minute: datetime
    confirmed_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "locator_key": self.locator_key,
            "available_minute": self.available_minute.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, str]) -> "ConfirmedDramaMatch | None":
        locator_key = str(raw.get("locator_key") or "").strip()
        if not locator_key:
            return None
        try:
            available_minute = datetime.fromisoformat(raw["available_minute"])
            confirmed_at = datetime.fromisoformat(raw["confirmed_at"])
        except (KeyError, TypeError, ValueError):
            return None
        if available_minute.tzinfo is None or confirmed_at.tzinfo is None:
            return None
        return cls(locator_key, available_minute, confirmed_at)

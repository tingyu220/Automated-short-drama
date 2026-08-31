"""账户表分配历史领域对象。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AccountUsage:
    """一次已确认的账户 CID 使用记录。"""

    task_id: str
    drama_name: str
    usage_day: date
    cid: str
    role: str
    sheet_kind: str
    row_number: int

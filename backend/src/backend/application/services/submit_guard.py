"""最终提交安全开关。"""
from __future__ import annotations

from dataclasses import dataclass

FINAL_SUBMIT_DISABLED = "FINAL_SUBMIT_DISABLED"
REAL_ADAPTERS_DISABLED = "REAL_ADAPTERS_DISABLED"


@dataclass(frozen=True)
class SubmitDecision:
    """提交放行决策。"""

    allowed: bool
    reason: str = ""


def can_submit(allow_final_submit: bool, use_real_adapters: bool) -> SubmitDecision:
    """最终提交开关与真实适配器开关同时开启才允许提交。"""
    if not allow_final_submit:
        return SubmitDecision(allowed=False, reason=FINAL_SUBMIT_DISABLED)
    if not use_real_adapters:
        return SubmitDecision(allowed=False, reason=REAL_ADAPTERS_DISABLED)
    return SubmitDecision(allowed=True)

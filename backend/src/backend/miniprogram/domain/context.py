"""MiniProgram 任务执行上下文。

只描述一次任务执行所需输入，不存 Native 业务数据。
唯一允许跨域读取：album_id。
"""
from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_PRICE_TIERS: list[str] = ["2.9", "9.9"]


@dataclass
class MiniProgramContext:
    """MiniProgram 一次任务执行的输入上下文。"""

    task_id: str
    drama_name: str
    operator_name: str
    operator_code: str
    organization_group: str
    organization_path: str
    required_price_tiers: list[str] = field(
        default_factory=lambda: list(DEFAULT_PRICE_TIERS)
    )
    album_id: str | None = None
    drama_short_name: str | None = None

    def validate(self) -> list[str]:
        """校验上下文完整性，返回错误列表。"""
        errors: list[str] = []
        if not self.task_id:
            errors.append("task_id 不能为空")
        if not self.drama_name:
            errors.append("drama_name 不能为空")
        if not self.operator_name:
            errors.append("operator_name 不能为空")
        if not self.operator_code:
            errors.append("operator_code 不能为空")
        if not self.required_price_tiers:
            errors.append("required_price_tiers 不能为空")
        return errors

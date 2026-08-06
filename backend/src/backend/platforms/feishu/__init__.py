"""飞书平台真实 Adapter 包."""

from backend.platforms.feishu.feishu_adapter import FeishuAdapter
from backend.platforms.feishu.sheet_parser import parse_task_rows

__all__ = ["FeishuAdapter", "parse_task_rows"]

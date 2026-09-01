"""MiniProgram 命名服务。

负责生成：
- Promotion Title: {operator_code}-{完整剧名}-{price_tier}
- Operator Code: 中文姓名转拼音首字母大写

生成后保存到 Context，不在每个步骤重复生成。
"""
from __future__ import annotations

import unicodedata


_PINYIN_FIRST_LETTER: dict[str, str] = {
    "田": "T", "雨": "Y", "施": "S", "凯": "K", "波": "B",
    "赖": "L", "亚": "Y", "健": "J", "甘": "G", "心": "X",
    "远": "Y", "高": "G", "有": "Y", "闯": "C",
    "李": "L", "明": "M", "张": "Z", "王": "W", "刘": "L",
    "陈": "C", "杨": "Y", "黄": "H", "赵": "Z", "周": "Z",
    "吴": "W", "徐": "X", "孙": "S", "胡": "H", "朱": "Z",
    "何": "H", "林": "L", "罗": "L", "郑": "Z", "梁": "L",
}


def resolve_operator_code(operator_name: str) -> str:
    """中文姓名转拼音首字母大写。

    例：田雨 → TY
    """
    if not operator_name:
        return ""
    parts: list[str] = []
    for ch in operator_name:
        if ch in _PINYIN_FIRST_LETTER:
            parts.append(_PINYIN_FIRST_LETTER[ch])
        elif ch.isascii() and ch.isalpha():
            parts.append(ch.upper())
    return "".join(parts)


def build_promotion_title(
    operator_code: str,
    drama_name: str,
    price_tier: str,
) -> str:
    """生成推广标题。

    格式：{operator_code}-{完整剧名}-{price_tier}
    例：TY-悍妇儿媳掌全局-2.9

    Args:
        operator_code: 投手编码，如 "TY"
        drama_name: 完整剧名
        price_tier: 价格档位，如 "2.9"

    Returns:
        推广标题字符串
    """
    parts = [p for p in (operator_code, drama_name, price_tier) if p]
    return "-".join(parts)


def resolve_short_name(drama_name: str, existing_short_name: str | None = None) -> tuple[str, str]:
    """解析短剧简称。

    M0 规则：
    - 已有 short_name → 复用，状态 READY
    - 没有 → 返回 NEEDS_CONFIRMATION，不自动生成

    Args:
        drama_name: 完整剧名
        existing_short_name: 已有的简称（可选）

    Returns:
        (short_name, status) — status 为 "READY" 或 "NEEDS_CONFIRMATION"
    """
    if existing_short_name:
        return existing_short_name, "READY"
    return drama_name, "NEEDS_CONFIRMATION"


class MiniProgramNamingService:
    """MiniProgram 命名服务。

    封装命名相关逻辑，便于未来扩展。
    """

    @staticmethod
    def operator_code(name: str) -> str:
        """中文姓名转拼音首字母。"""
        return resolve_operator_code(name)

    @staticmethod
    def promotion_title(operator_code: str, drama_name: str, price_tier: str) -> str:
        """生成推广标题。"""
        return build_promotion_title(operator_code, drama_name, price_tier)

    @staticmethod
    def short_name(drama_name: str, existing: str | None = None) -> tuple[str, str]:
        """解析短剧简称。"""
        return resolve_short_name(drama_name, existing)

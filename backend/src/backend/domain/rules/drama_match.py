"""同名剧按标准化剧名与上海时区分钟唯一匹配。"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

from backend.domain.common.timezones import SHANGHAI_TZ
from backend.domain.errors.domain_error import DramaMismatchError

MATCH_TIME_TOLERANCE_MINUTES = 5


@dataclass(frozen=True)
class DramaCandidate:
    """外部平台剧目候选；locator_key 只用于定位已确认候选。"""

    drama_name: str
    available_time: datetime
    locator_key: str
    raw_time: str
    page_order: int


def normalize_drama_name(value: str) -> str:
    """执行 Unicode 兼容归一化并移除空白，不做模糊匹配。"""
    return "".join(unicodedata.normalize("NFKC", value).split())


def shanghai_minute(value: datetime) -> datetime:
    """把带时区时间统一到上海时区并截断到分钟。"""
    if value.tzinfo is None:
        raise ValueError("剧目匹配时间必须包含时区")
    return value.astimezone(SHANGHAI_TZ).replace(second=0, microsecond=0)


def minute_difference(left: datetime, right: datetime) -> int:
    """返回两个已按分钟归一化时间的绝对分钟差。"""
    return int(abs((left - right).total_seconds()) // 60)


def match_unique_drama(
    expected_name: str,
    expected_time: datetime,
    candidates: list[DramaCandidate],
) -> DramaCandidate:
    """返回唯一同名同分钟候选；不确定时拒绝自动选择。"""
    try:
        expected_minute = shanghai_minute(expected_time)
    except ValueError as exc:
        raise DramaMismatchError(
            str(exc),
            details={"reason": "INVALID_EXPECTED_TIME"},
        ) from exc

    invalid = [item for item in candidates if item.available_time.tzinfo is None]
    if invalid:
        raise DramaMismatchError(
            "平台候选时间缺少时区",
            details={
                "reason": "INVALID_CANDIDATE_TIME",
                "raw_times": [item.raw_time for item in invalid],
            },
        )

    normalized_name = normalize_drama_name(expected_name)

    exact_matches = [
        item
        for item in candidates
        if normalize_drama_name(item.drama_name) == normalized_name
        and shanghai_minute(item.available_time) == expected_minute
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    exact_tolerance = [
        item
        for item in candidates
        if normalize_drama_name(item.drama_name) == normalized_name
        and minute_difference(
            shanghai_minute(item.available_time), expected_minute
        ) <= MATCH_TIME_TOLERANCE_MINUTES
    ]
    if len(exact_tolerance) == 1:
        return exact_tolerance[0]
    if len(exact_tolerance) > 1:
        raise DramaMismatchError(
            "同名剧分钟级匹配不唯一",
            details={
                "reason": "MULTIPLE_EXACT_MATCHES",
                "expected_name": expected_name,
                "expected_minute": expected_minute.isoformat(),
                "match_count": len(exact_tolerance),
                "candidates": _candidate_details(exact_tolerance, expected_minute),
            },
        )

    fuzzy_exact = [
        item
        for item in candidates
        if (
            normalized_name in normalize_drama_name(item.drama_name)
            or normalize_drama_name(item.drama_name) in normalized_name
        )
        and normalize_drama_name(item.drama_name) != normalized_name
        and shanghai_minute(item.available_time) == expected_minute
    ]
    if len(fuzzy_exact) == 1:
        return fuzzy_exact[0]

    fuzzy_tolerance = [
        item
        for item in candidates
        if (
            normalized_name in normalize_drama_name(item.drama_name)
            or normalize_drama_name(item.drama_name) in normalized_name
        )
        and normalize_drama_name(item.drama_name) != normalized_name
        and minute_difference(
            shanghai_minute(item.available_time), expected_minute
        ) <= MATCH_TIME_TOLERANCE_MINUTES
    ]
    if len(fuzzy_tolerance) == 1:
        return fuzzy_tolerance[0]
    if len(fuzzy_tolerance) > 1:
        return min(
            fuzzy_tolerance,
            key=lambda item: minute_difference(
                shanghai_minute(item.available_time), expected_minute
            ),
        )

    raise DramaMismatchError(
        "同名剧分钟级匹配不唯一",
        details={
            "reason": "NO_EXACT_MATCH",
            "expected_name": expected_name,
            "expected_minute": expected_minute.isoformat(),
            "match_count": 0,
            "candidates": _candidate_details(candidates, expected_minute),
        },
    )


def _candidate_details(
    candidates: list[DramaCandidate], expected_minute: datetime
) -> list[dict]:
    return [
        {
            "drama_name": item.drama_name,
            "minute": shanghai_minute(item.available_time).isoformat(),
            "time_difference_minutes": minute_difference(
                shanghai_minute(item.available_time), expected_minute
            ),
            "raw_time": item.raw_time,
            "locator_key": item.locator_key,
            "page_order": item.page_order,
        }
        for item in candidates
    ]

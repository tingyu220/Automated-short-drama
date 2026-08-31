"""同名剧按上海时区分钟唯一匹配的领域测试。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.common.timezones import SHANGHAI_TZ
from backend.domain.errors.domain_error import DramaMismatchError
from backend.domain.rules.drama_match import DramaCandidate, match_unique_drama


def _candidate(
    name: str,
    minute: datetime,
    locator_key: str,
    *,
    raw_time: str = "2026-08-10 14:30",
    page_order: int = 0,
) -> DramaCandidate:
    return DramaCandidate(name, minute, locator_key, raw_time, page_order)


def test_match_uses_normalized_name_and_shanghai_minute() -> None:
    """防止全角字符、空白和秒数导致唯一候选漏选。"""
    expected = datetime(2026, 8, 10, 6, 30, 59, tzinfo=timezone.utc)
    candidates = [
        _candidate(
            " 剧Ａ ",
            datetime(2026, 8, 10, 14, 30, 1, tzinfo=SHANGHAI_TZ),
            "/detail/right",
        ),
        _candidate(
            "剧A",
            datetime(2026, 8, 10, 14, 31, tzinfo=SHANGHAI_TZ),
            "/detail/later",
            raw_time="2026-08-10 14:31",
            page_order=1,
        ),
    ]

    matched = match_unique_drama("剧A", expected, candidates)

    assert matched.locator_key == "/detail/right"


def test_same_name_candidate_outside_tolerance_is_not_selected_as_nearest() -> None:
    """超出正常偏差窗口时不能按最近时间自动选择。"""
    expected = datetime(2026, 8, 10, 6, 30, tzinfo=timezone.utc)
    candidates = [
        _candidate(
            "剧A",
            datetime(2026, 8, 10, 14, 24, tzinfo=SHANGHAI_TZ),
            "/detail/near",
            raw_time="2026-08-10 14:24",
        )
    ]

    with pytest.raises(DramaMismatchError) as caught:
        match_unique_drama("剧A", expected, candidates)

    assert caught.value.code == "DRAMA_MISMATCH"
    assert caught.value.details["match_count"] == 0


def test_unique_same_name_candidate_within_five_minutes_matches() -> None:
    """番茄正常提前两分钟上架时，唯一同名候选可以自动通过。"""
    expected = datetime(2026, 8, 19, 0, 55, tzinfo=SHANGHAI_TZ)
    candidate = _candidate(
        "剧A",
        datetime(2026, 8, 19, 0, 53, tzinfo=SHANGHAI_TZ),
        "/detail/early",
        raw_time="2026-08-19 00:53",
    )

    matched = match_unique_drama("剧A", expected, [candidate])

    assert matched == candidate


def test_same_name_candidate_outside_five_minutes_is_rejected() -> None:
    """超出正常偏差窗口时不能按最近时间自动选择。"""
    expected = datetime(2026, 8, 19, 0, 55, tzinfo=SHANGHAI_TZ)
    candidate = _candidate(
        "剧A",
        datetime(2026, 8, 19, 0, 49, tzinfo=SHANGHAI_TZ),
        "/detail/too-early",
        raw_time="2026-08-19 00:49",
    )

    with pytest.raises(DramaMismatchError) as caught:
        match_unique_drama("剧A", expected, [candidate])

    assert caught.value.details["reason"] == "NO_EXACT_MATCH"


def test_multiple_same_name_candidates_within_five_minutes_are_rejected() -> None:
    """时间容差不能让同名候选退化为按页面顺序选择。"""
    expected = datetime(2026, 8, 19, 0, 55, tzinfo=SHANGHAI_TZ)
    candidates = [
        _candidate(
            "剧A",
            datetime(2026, 8, 19, 0, 53, tzinfo=SHANGHAI_TZ),
            "/detail/early",
        ),
        _candidate(
            "剧A",
            datetime(2026, 8, 19, 0, 56, tzinfo=SHANGHAI_TZ),
            "/detail/late",
            page_order=1,
        ),
    ]

    with pytest.raises(DramaMismatchError) as caught:
        match_unique_drama("剧A", expected, candidates)

    assert caught.value.details["reason"] == "MULTIPLE_EXACT_MATCHES"


def test_multiple_exact_matches_are_rejected() -> None:
    """防止异常重复数据时默认点击首条。"""
    expected = datetime(2026, 8, 10, 6, 30, tzinfo=timezone.utc)
    exact_minute = datetime(2026, 8, 10, 14, 30, tzinfo=SHANGHAI_TZ)
    candidates = [
        _candidate("剧A", exact_minute, "/detail/one", page_order=0),
        _candidate("剧A", exact_minute, "/detail/two", page_order=1),
    ]

    with pytest.raises(DramaMismatchError) as caught:
        match_unique_drama("剧A", expected, candidates)

    assert caught.value.details["match_count"] == 2
    assert [row["locator_key"] for row in caught.value.details["candidates"]] == [
        "/detail/one",
        "/detail/two",
    ]


def test_naive_candidate_time_is_rejected() -> None:
    """防止缺失时区的数据被静默猜测为某个业务时区。"""
    candidate = _candidate(
        "剧A",
        datetime(2026, 8, 10, 14, 30),
        "/detail/no-timezone",
    )

    with pytest.raises(DramaMismatchError) as caught:
        match_unique_drama(
            "剧A",
            datetime(2026, 8, 10, 6, 30, tzinfo=timezone.utc),
            [candidate],
        )

    assert caught.value.details["reason"] == "INVALID_CANDIDATE_TIME"

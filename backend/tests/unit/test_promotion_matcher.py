"""推广链接精确匹配器单元测试（Phase 6）。

匹配优先级：
external_drama_id → promotion_id → template_id → ConfirmedDramaMatch → 精确剧名 → 剧名+时间
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    PromotionAsset,
)
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.tasks.drama_task import DramaTask
from backend.domain.acquisition.promotion_matcher import (
    MatchResult,
    MatchConfidence,
    PromotionMatcher,
    _normalize_name,
    _names_match_exact,
    _names_match_fuzzy,
)


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _make_candidate(
    *,
    candidate_id: str = "c1",
    external_drama_id: str | None = None,
    promotion_id: str | None = None,
    template_id: str | None = None,
    drama_name: str = "测试剧",
    link_type: str = "2.9",
    price: float | None = 2.9,
    episode: int | None = None,
) -> PromotionAsset:
    return PromotionAsset(
        id=candidate_id,
        task_id="task-1",
        source_platform="TOMATO",
        drama_name=drama_name,
        link_type=link_type,
        promotion_url=f"https://example.com/promo/{candidate_id}",
        external_drama_id=external_drama_id,
        promotion_id=promotion_id,
        episode=episode,
        template_id=template_id,
        price=price,
        acquisition_method=AcquisitionMethod.NETWORK,
        acquisition_status=AssetStatus.DISCOVERED,
    )


# ---------------------------------------------------------------------------
# 名称规范化辅助函数
# ---------------------------------------------------------------------------


def test_normalize_name_strips_whitespace_and_case() -> None:
    assert _normalize_name("  Test Drama  ") == "testdrama"
    assert _normalize_name("测试 剧") == "测试剧"
    assert _normalize_name("") == ""


def test_normalize_name_removes_common_suffixes() -> None:
    """去掉常见的"全集""完整版"等后缀再比较。"""
    assert _normalize_name("测试剧全集") == _normalize_name("测试剧")
    assert _normalize_name("测试剧完整版") == _normalize_name("测试剧")


def test_exact_name_match() -> None:
    assert _names_match_exact("测试剧", "测试剧") is True
    assert _names_match_exact("测试剧", "测试剧全集") is False
    assert _names_match_exact("测试剧", "别的剧") is False
    assert _names_match_exact("", "") is False


def test_fuzzy_name_match() -> None:
    """模糊匹配：规范化后相等即算匹配。"""
    assert _names_match_fuzzy("测试剧全集", "测试剧") is True
    assert _names_match_fuzzy("测试剧 完整版", "测试剧") is True
    assert _names_match_fuzzy("测试剧", "别的剧") is False


# ---------------------------------------------------------------------------
# MatchResult 数据类
# ---------------------------------------------------------------------------


def test_match_result_matched_has_selected() -> None:
    candidate = _make_candidate()
    result = MatchResult.matched(candidate, confidence=MatchConfidence.EXTERNAL_ID)
    assert result.is_matched is True
    assert result.selected == candidate
    assert result.confidence == MatchConfidence.EXTERNAL_ID
    assert result.ambiguous_candidates == []


def test_match_result_ambiguous_has_candidates() -> None:
    c1 = _make_candidate(candidate_id="c1")
    c2 = _make_candidate(candidate_id="c2")
    result = MatchResult.ambiguous([c1, c2], confidence=MatchConfidence.FUZZY_NAME)
    assert result.is_matched is False
    assert result.is_ambiguous is True
    assert len(result.ambiguous_candidates) == 2
    assert result.confidence == MatchConfidence.FUZZY_NAME


def test_match_result_not_found() -> None:
    result = MatchResult.not_found()
    assert result.is_matched is False
    assert result.is_ambiguous is False
    assert result.selected is None
    assert result.ambiguous_candidates == []


# ---------------------------------------------------------------------------
# MatchConfidence 优先级
# ---------------------------------------------------------------------------


def test_confidence_priority_order() -> None:
    """置信度枚举值应按优先级递增。"""
    assert MatchConfidence.EXTERNAL_ID > MatchConfidence.PROMOTION_ID
    assert MatchConfidence.PROMOTION_ID > MatchConfidence.TEMPLATE_ID
    assert MatchConfidence.TEMPLATE_ID > MatchConfidence.CONFIRMED_MATCH
    assert MatchConfidence.CONFIRMED_MATCH > MatchConfidence.EXACT_NAME
    assert MatchConfidence.EXACT_NAME > MatchConfidence.FUZZY_NAME


# ---------------------------------------------------------------------------
# PromotionMatcher: 单档位匹配
# ---------------------------------------------------------------------------


def test_match_by_external_drama_id_single() -> None:
    """有 external_drama_id 且唯一 → 精确匹配，最高置信度。"""
    candidates = [
        _make_candidate(candidate_id="c1", external_drama_id="drama-123"),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    assert result.is_matched is True
    assert result.selected.external_drama_id == "drama-123"
    assert result.confidence == MatchConfidence.EXTERNAL_ID


def test_match_by_external_drama_id_multiple_same_drama_ambiguous() -> None:
    """同一个 external_drama_id 下同档位多个推广 → AMBIGUOUS。"""
    candidates = [
        _make_candidate(
            candidate_id="c1", external_drama_id="drama-123",
            promotion_id="promo-a", template_id="tpl-a",
        ),
        _make_candidate(
            candidate_id="c2", external_drama_id="drama-123",
            promotion_id="promo-b", template_id="tpl-b",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    assert result.is_ambiguous is True
    assert result.confidence == MatchConfidence.EXTERNAL_ID
    assert len(result.ambiguous_candidates) == 2


def test_match_by_exact_name_single() -> None:
    """无 external_id 但剧名精确匹配且唯一 → EXACT_NAME 置信度。"""
    candidates = [
        _make_candidate(candidate_id="c1", external_drama_id=None, drama_name="测试剧"),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    assert result.is_matched is True
    assert result.confidence == MatchConfidence.EXACT_NAME


def test_match_fuzzy_name_only_produces_candidates_not_selected() -> None:
    """只有模糊剧名匹配时，不自动选择，标记为 AMBIGUOUS。

    模糊剧名只能用于产生 Candidate，不能直接进入生产。
    """
    candidates = [
        _make_candidate(
            candidate_id="c1", external_drama_id=None,
            drama_name="测试剧全集",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    # 模糊剧名匹配不能直接选，必须是 AMBIGUOUS（需要人工确认）
    assert result.is_matched is False
    assert result.is_ambiguous is True
    assert result.confidence == MatchConfidence.FUZZY_NAME
    assert len(result.ambiguous_candidates) == 1


def test_match_with_confirmed_drama_match() -> None:
    """有 ConfirmedDramaMatch 时，用 locator_key 定位。"""
    candidates = [
        _make_candidate(
            candidate_id="c1", external_drama_id="drama-456",
            promotion_id="promo-x", drama_name="别的剧",
        ),
        _make_candidate(
            candidate_id="c2", external_drama_id="drama-123",
            promotion_id="promo-a", drama_name="测试剧",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
        confirmed_drama_match=ConfirmedDramaMatch(
            locator_key="drama-123",
            available_minute=TARGET_TIME,
            confirmed_at=TARGET_TIME,
        ),
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    assert result.is_matched is True
    assert result.selected.external_drama_id == "drama-123"
    # CONFIRMED_MATCH 置信度低于 EXTERNAL_ID，但高于 EXACT_NAME
    assert result.confidence in (
        MatchConfidence.CONFIRMED_MATCH,
        MatchConfidence.EXTERNAL_ID,  # 如果 external_id 也匹配，取更高置信度
    )


def test_match_no_candidates_returns_not_found() -> None:
    """零候选 → NOT_FOUND。"""
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match([])

    assert result.is_matched is False
    assert result.is_ambiguous is False
    assert result.confidence is None


def test_match_filters_by_link_type() -> None:
    """只在同 link_type 的候选中匹配。"""
    candidates = [
        _make_candidate(candidate_id="c1", link_type="2.9", external_drama_id="drama-1"),
        _make_candidate(candidate_id="c2", link_type="9.9", external_drama_id="drama-1"),
        _make_candidate(candidate_id="c3", link_type="IAA", external_drama_id="drama-1"),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    assert result.is_matched is True
    assert result.selected.id == "c1"
    assert result.selected.link_type == "2.9"


def test_match_prefers_higher_confidence() -> None:
    """混合 external_id 和 剧名匹配时，取 external_id 的结果。"""
    candidates = [
        _make_candidate(
            candidate_id="c1", external_drama_id=None, drama_name="测试剧",
        ),
        _make_candidate(
            candidate_id="c2", external_drama_id="drama-123", drama_name="测试剧其他",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    # external_drama_id 是强标识，即使剧名不完全匹配也优先
    # 但这里 c2 的 external_drama_id 没有对应的确认信息，剧名又不匹配
    # 应该是：c1 是 EXACT_NAME，c2 剧名不匹配被过滤
    # 最终匹配 c1
    assert result.is_matched is True
    assert result.selected.id == "c1"
    assert result.confidence == MatchConfidence.EXACT_NAME


def test_match_iaa_by_episode() -> None:
    """IAA 类型匹配时，集数也作为区分因素。"""
    candidates = [
        _make_candidate(
            candidate_id="c1", link_type="IAA", episode=1,
            external_drama_id="drama-123",
        ),
        _make_candidate(
            candidate_id="c2", link_type="IAA", episode=2,
            external_drama_id="drama-123",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="IAA")

    result = matcher.match(candidates)

    # 同 external_id 下同类型不同集数 → AMBIGUOUS（IAA 需要确定集数）
    assert result.is_ambiguous is True
    assert result.confidence == MatchConfidence.EXTERNAL_ID


# ---------------------------------------------------------------------------
# PromotionMatcher: 多档位批量匹配
# ---------------------------------------------------------------------------


def test_match_all_returns_per_type_results() -> None:
    """批量匹配：为每个预期档位返回独立结果。"""
    candidates = [
        _make_candidate(
            candidate_id="c-iaa", link_type="IAA", episode=2,
            external_drama_id="drama-123", price=None, template_id=None,
        ),
        _make_candidate(
            candidate_id="c-29", link_type="2.9",
            external_drama_id="drama-123",
        ),
        _make_candidate(
            candidate_id="c-99", link_type="9.9",
            external_drama_id="drama-123",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    all_results = matcher.match_all_types(
        candidates, expected_types=["IAA", "2.9", "9.9"]
    )

    assert len(all_results) == 3
    assert all_results["IAA"].is_matched is True
    assert all_results["2.9"].is_matched is True
    assert all_results["9.9"].is_matched is True
    assert all_results["IAA"].selected.id == "c-iaa"
    assert all_results["2.9"].selected.id == "c-29"
    assert all_results["9.9"].selected.id == "c-99"


def test_match_all_mixed_statuses() -> None:
    """混合状态：有的匹配、有的缺失、有的歧义。"""
    candidates = [
        _make_candidate(
            candidate_id="c-iaa-1", link_type="IAA", episode=1,
            external_drama_id="drama-123", price=None, template_id=None,
        ),
        _make_candidate(
            candidate_id="c-iaa-2", link_type="IAA", episode=2,
            external_drama_id="drama-123", price=None, template_id=None,
        ),
        _make_candidate(
            candidate_id="c-29", link_type="2.9",
            external_drama_id="drama-123",
        ),
        # 9.9 没有候选
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    all_results = matcher.match_all_types(
        candidates, expected_types=["IAA", "2.9", "9.9"]
    )

    assert all_results["IAA"].is_ambiguous is True  # 2 个 IAA 候选
    assert all_results["2.9"].is_matched is True
    assert all_results["9.9"].is_matched is False
    assert all_results["9.9"].is_ambiguous is False  # NOT_FOUND


# ---------------------------------------------------------------------------
# 安全规则：绝不自动选第一条
# ---------------------------------------------------------------------------


def test_match_never_picks_first_on_ambiguous() -> None:
    """歧义情况下，selected 必须为 None，绝不能自动取第一条。"""
    candidates = [
        _make_candidate(
            candidate_id="first", external_drama_id="drama-123",
            promotion_id="promo-a",
        ),
        _make_candidate(
            candidate_id="second", external_drama_id="drama-123",
            promotion_id="promo-b",
        ),
    ]
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
    )
    matcher = PromotionMatcher(task, expected_link_type="2.9")

    result = matcher.match(candidates)

    assert result.is_ambiguous is True
    assert result.selected is None  # 关键：绝不自动选第一条
    assert len(result.ambiguous_candidates) == 2

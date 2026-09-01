"""验证 Matcher 不会仅凭 Candidate 有 promotion_id 就匹配，需要 Expected ID。"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.domain.acquisition.promotion_matcher import (
    MatchConfidence,
    PromotionMatcher,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.tasks.drama_task import DramaTask


def _task(confirmed_match=None):
    return DramaTask(
        id="t1",
        sheet_row=1,
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links={},
        confirmed_drama_match=confirmed_match,
    )


def _asset(link_type="IAA", promotion_id="p1", drama_name="剧A", template_id=None, external_drama_id="d1"):
    return PromotionAsset(
        id=str(uuid4()),
        task_id="t1",
        source_platform="TOMATO",
        drama_name=drama_name,
        link_type=link_type,
        promotion_url="aweme://playlet?x=1",
        promotion_id=promotion_id,
        template_id=template_id,
        external_drama_id=external_drama_id,
        acquisition_method=AcquisitionMethod.NETWORK,
        acquisition_status=AssetStatus.DISCOVERED,
        verification_status=VerificationStatus.UNVERIFIED,
        created_or_existing=CreationStatus.EXISTING,
    )


class TestMatcherRequiresExpectedId:
    """Phase 9: Matcher 需要 Expected ID 才能做 ID 级匹配。"""

    def test_promotion_id_not_matched_without_confirmed(self):
        """无 confirmed_match → promotion_id 匹配跳过，不自动选有 promotion_id 的。"""
        task = _task(confirmed_match=None)
        matcher = PromotionMatcher(task, expected_link_type="IAA")

        candidates = [_asset(promotion_id="p1"), _asset(promotion_id="p2")]
        result = matcher.match(candidates)

        # Should NOT match by promotion_id alone → ambiguous or not_found
        assert not result.is_matched or result.is_ambiguous

    def test_promotion_id_matched_with_confirmed(self):
        """有 confirmed_match 且 locator_key 匹配 → promotion_id 匹配成功。"""
        confirmed = type("ConfirmedMatch", (), {"locator_key": "p1"})()
        task = _task(confirmed_match=confirmed)
        matcher = PromotionMatcher(task, expected_link_type="IAA")

        candidates = [_asset(promotion_id="p1"), _asset(promotion_id="p2")]
        result = matcher.match(candidates)

        assert result.is_matched
        assert result.selected.promotion_id == "p1"

    def test_template_id_not_matched_without_confirmed(self):
        """无 confirmed_match → template_id 匹配跳过。"""
        task = _task(confirmed_match=None)
        matcher = PromotionMatcher(task, expected_link_type="2.9")

        candidates = [_asset(link_type="2.9", promotion_id="p1", template_id="t1")]
        result = matcher.match(candidates)

        # Without confirmed_match, template_id matching should be skipped
        # Falls through to exact_name match (drama_name="剧A" matches task.drama_name="剧A")
        assert result.is_matched

    def test_exact_name_still_works_without_confirmed(self):
        """无 confirmed_match → 精确剧名匹配仍然工作。"""
        task = _task(confirmed_match=None)
        matcher = PromotionMatcher(task, expected_link_type="IAA")

        candidates = [_asset(drama_name="剧A", promotion_id=None, external_drama_id=None)]
        result = matcher.match(candidates)

        assert result.is_matched
        assert result.confidence == MatchConfidence.EXACT_NAME

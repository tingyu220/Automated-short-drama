"""验证 Candidate 缺少剧名时不自动从 task 补值。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.platforms.tomato.network.response_parser import ParsedPromotion
from backend.platforms.tomato.providers.network_provider import _to_asset
from backend.domain.tasks.drama_task import DramaTask


def _task():
    return DramaTask(
        id="t1",
        sheet_row=1,
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links={},
    )


class TestCandidateMissingIdentityNotAutoFilled:
    """Phase 8: Candidate 身份修复 — 禁止自动补值。"""

    def test_empty_drama_name_not_filled_from_task(self):
        """ParsedPromotion 无 drama_name → asset.drama_name 为空，不从 task 补。"""
        parsed = ParsedPromotion(
            promotion_id="p1",
            drama_name="",
            link_type="IAA",
            promotion_url="aweme://playlet?x=1",
            external_drama_id="d1",
        )
        asset = _to_asset(_task(), parsed, "IAA")
        assert asset.drama_name == ""

    def test_drama_name_from_response_preserved(self):
        """ParsedPromotion 有 drama_name → asset.drama_name 保留响应值。"""
        parsed = ParsedPromotion(
            promotion_id="p1",
            drama_name="剧A",
            link_type="IAA",
            promotion_url="aweme://playlet?x=1",
            external_drama_id="d1",
        )
        asset = _to_asset(_task(), parsed, "IAA")
        assert asset.drama_name == "剧A"

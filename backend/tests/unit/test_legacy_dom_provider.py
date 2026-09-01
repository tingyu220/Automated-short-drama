"""旧番茄 DOM 链路 Provider 包装测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    CreationStatus,
)
from backend.domain.ports.adapters import PromotionLink, TemplateInfo
from backend.domain.rules.confirmed_drama_match import ConfirmedDramaMatch
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.tomato.providers.legacy_dom_provider import LegacyDomProvider


TARGET_TIME = datetime(2026, 8, 31, tzinfo=timezone.utc)


class RecordingTomato:
    """记录旧链路收到的确定性剧目上下文。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get_episode_count(self, drama_name, available_time, confirmed_match=None):
        self.calls.append(("episode", drama_name, available_time, confirmed_match))
        return 60

    def extract_iaa_link(
        self,
        drama_name,
        available_time,
        episode_count,
        selected_episode,
        confirmed_match=None,
    ):
        self.calls.append(
            (
                "iaa",
                drama_name,
                available_time,
                episode_count,
                selected_episode,
                confirmed_match,
            )
        )
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA",
            promotion_url="mock://iaa/测试剧?ep=2",
            source_platform="TOMATO",
            source_entry="FREE",
            acquisition_method="PROMOTION_LIST_VIEW",
        )

    def scan_iap_templates(self, drama_name, available_time, confirmed_match=None):
        self.calls.append(("templates", drama_name, available_time, confirmed_match))
        return [TemplateInfo("tpl-2.9", drama_name, "2.9模板", 2.9, 1)]

    def generate_iap_link(
        self,
        drama_name,
        available_time,
        template,
        confirmed_match=None,
        **kwargs,
    ):
        self.calls.append(
            (
                "iap",
                drama_name,
                available_time,
                template.template_id,
                confirmed_match,
            )
        )
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAP",
            promotion_url="mock://iap/测试剧?tpl=tpl-2.9",
            source_platform="TOMATO",
            source_entry="PAID",
            acquisition_method="PAGE_EXTRACTION",
        )


def _rules() -> list[TemplatePriceRule]:
    return [
        TemplatePriceRule(
            key="iap_2_9",
            target_price=2.9,
            min_price=2.6,
            max_price=5.0,
        )
    ]


def test_provider_wraps_legacy_links_as_assets() -> None:
    result = LegacyDomProvider(RecordingTomato(), _rules()).acquire(
        DramaTask(
            id="task-1",
            drama_name="测试剧",
            platform="TOMATO",
            available_time=TARGET_TIME,
        )
    )

    assert result.expected_types == ["IAA", "2.9"]
    assert [asset.link_type for asset in result.candidates] == ["IAA", "2.9"]
    assert all(
        asset.acquisition_method == AcquisitionMethod.LEGACY
        for asset in result.candidates
    )
    assert result.candidates[0].created_or_existing == CreationStatus.EXISTING
    assert result.candidates[1].template_id == "tpl-2.9"


def test_provider_passes_confirmed_match_through_every_legacy_operation() -> None:
    confirmation = ConfirmedDramaMatch(
        locator_key="/detail/1",
        available_minute=TARGET_TIME,
        confirmed_at=TARGET_TIME,
    )
    tomato = RecordingTomato()
    task = DramaTask(
        id="task-1",
        drama_name="测试剧",
        platform="TOMATO",
        available_time=TARGET_TIME,
        confirmed_drama_match=confirmation,
    )

    LegacyDomProvider(tomato, _rules()).acquire(task)

    assert tomato.calls == [
        ("episode", "测试剧", TARGET_TIME, confirmation),
        ("iaa", "测试剧", TARGET_TIME, 60, 2, confirmation),
        ("templates", "测试剧", TARGET_TIME, confirmation),
        ("iap", "测试剧", TARGET_TIME, "tpl-2.9", confirmation),
    ]


def test_provider_keeps_correct_template_when_other_bucket_generation_fails() -> None:
    class PartialTomato(RecordingTomato):
        def scan_iap_templates(self, drama_name, available_time, confirmed_match=None):
            return [
                TemplateInfo("tpl-2.9", drama_name, "2.9模板", 2.9, 1),
                TemplateInfo("tpl-9.9", drama_name, "9.9模板", 9.9, 2),
            ]

        def generate_iap_link(
            self,
            drama_name,
            available_time,
            template,
            confirmed_match=None,
            **kwargs,
        ):
            if template.template_id == "tpl-2.9":
                raise TimeoutError("2.9 生成失败")
            return PromotionLink(
                drama_name=drama_name,
                link_type="IAP",
                promotion_url="mock://iap/测试剧?tpl=tpl-9.9",
                source_platform="TOMATO",
                source_entry="PAID",
            )

    rules = _rules() + [
        TemplatePriceRule(
            key="iap_9_9",
            target_price=9.9,
            min_price=8.8,
            max_price=13.8,
        )
    ]

    result = LegacyDomProvider(PartialTomato(), rules).acquire(
        DramaTask(
            id="task-1",
            drama_name="测试剧",
            platform="TOMATO",
            available_time=TARGET_TIME,
        )
    )

    paid = next(asset for asset in result.candidates if asset.link_type == "9.9")
    assert paid.template_id == "tpl-9.9"

"""番茄 Adapter Mock 实现 —— 确定性链接与模板，无网络."""
from __future__ import annotations

from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter


class MockTomatoAdapter(TomatoAdapter):
    """确定性番茄链接提取 Mock."""

    def extract_iaa_link(
        self,
        drama_name: str,
        episode_count: int,
        selected_episode: int,
    ) -> PromotionLink:
        del episode_count  # 无网络 Mock 不参与选集决策
        url = f"mock://iaa/{drama_name}?ep={selected_episode}"
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAA",
            promotion_url=url,
            source_platform="TOMATO",
            source_entry="FREE",
            acquisition_method="MOCK",
            source_column="J",
            url_length=len(url),
            link_status="OK",
        )

    def scan_iap_templates(self, drama_name: str) -> list[TemplateInfo]:
        return [
            TemplateInfo(
                template_id=f"tpl-{drama_name}-2-9",
                drama_name=drama_name,
                title="2.9 档模板",
                price=2.9,
                page_order=1,
            ),
            TemplateInfo(
                template_id=f"tpl-{drama_name}-9-9",
                drama_name=drama_name,
                title="9.9 档模板",
                price=9.9,
                page_order=2,
            ),
            TemplateInfo(
                template_id=f"tpl-{drama_name}-out",
                drama_name=drama_name,
                title="区间外模板",
                price=25.0,
                page_order=3,
            ),
        ]

    def generate_iap_link(self, drama_name: str, template: TemplateInfo) -> PromotionLink:
        url = f"mock://iap/IAP/{drama_name}?tpl={template.template_id}"
        return PromotionLink(
            drama_name=drama_name,
            link_type="IAP",
            promotion_url=url,
            source_platform="TOMATO",
            source_entry="PAID",
            acquisition_method="MOCK",
            source_column="K",
            url_length=len(url),
            link_status="OK",
        )

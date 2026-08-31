"""youxuan2 Adapter Mock 实现 —— 确定性链接，无网络."""
from __future__ import annotations

from backend.domain.ports.adapters import PromotionLink, YouxuanAdapter


class MockYouxuanAdapter(YouxuanAdapter):
    """确定性 youxuan2 链接搭建 Mock."""

    def extract_links(self, drama_name: str) -> list[PromotionLink]:
        url = f"mock://youxuan/{drama_name}"
        return [
            PromotionLink(
                drama_name=drama_name,
                link_type="IAA",
                promotion_url=url,
                source_platform="YOUXUAN",
                source_entry="MINIPROGRAM",
                acquisition_method="MOCK",
                url_length=len(url),
                link_status="OK",
            )
        ]

"""投放系统剧目资源页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError
from backend.domain.ports.adapters import DramaAsset


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"


class DramaAssetPage:
    """剧目资源操作：搜索、创建、按名称幂等获取."""

    def __init__(self, page: Any, selectors: dict[str, str]) -> None:
        self._page = page
        self._selectors = selectors

    def search(self, drama_name: str) -> bool:
        """按剧名搜索剧目资源，命中详情字段且有 delivery_drama_id 才算存在."""
        self._page.goto(self._selectors["base_url"])
        self._page.locator(self._selectors["asset_search_input"]).fill(drama_name)
        self._page.locator(self._selectors["asset_search_button"]).click()
        field = self._page.locator(self._selectors["delivery_drama_id_field"])
        if field.count() == 0:
            return False
        return bool((field.input_value() or "").strip())

    def create(self, link: str) -> DramaAsset:
        """创建剧目资源并读取 delivery_drama_id/album_id."""
        self._page.locator(self._selectors["asset_create_button"]).click()
        self._page.locator(self._selectors["asset_link_input"]).fill(link)
        self._page.locator(self._selectors["asset_save_button"]).click()
        delivery_drama_id = (
            self._page.locator(self._selectors["delivery_drama_id_field"]).input_value()
            or ""
        ).strip()
        album_id = (
            self._page.locator(self._selectors["album_id_field"]).input_value() or ""
        ).strip()
        if not delivery_drama_id:
            raise ExternalAdapterError(
                "剧目资源创建后未读到 delivery_drama_id，结果不确定",
                code=RESULT_UNCERTAIN,
            )
        return DramaAsset(
            delivery_drama_id=delivery_drama_id,
            drama_name="",
            link=link,
            album_id=album_id,
        )

    def find_or_create(self, drama_name: str, link: str) -> DramaAsset:
        """存在则复用，不存在则创建，保证按名称幂等."""
        if self.search(drama_name):
            asset = DramaAsset(
                delivery_drama_id=(
                    self._page.locator(
                        self._selectors["delivery_drama_id_field"]
                    ).input_value()
                    or ""
                ).strip(),
                drama_name=drama_name,
                link=link,
                album_id=(
                    self._page.locator(self._selectors["album_id_field"]).input_value()
                    or ""
                ).strip(),
            )
            return asset
        asset = self.create(link)
        asset.drama_name = drama_name
        return asset

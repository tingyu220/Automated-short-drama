"""巨量产品库页面对象."""
from __future__ import annotations

from typing import Any

from backend.domain.errors.domain_error import ExternalAdapterError


RESULT_UNCERTAIN = "RESULT_UNCERTAIN"
DEFAULT_CARRIER = "端原生"
DEFAULT_COPYRIGHT = "厦门骑驰网络科技有限公司"
DEFAULT_MONETIZATION = "付费变现+流量变现"


class ProductLibraryPage:
    """巨量产品库操作：按固定路径导航、创建产品并按产品 ID 验证."""

    def __init__(self, page: Any, selectors: dict[str, Any]) -> None:
        self._page = page
        self._selectors = selectors

    def navigate(self) -> None:
        """进入固定产品库：杨硕总体户→B组李伟层级→资产→商品管理→通用版→lw全域ROI3产品库."""
        self._page.goto(self._selectors["base_url"])
        for label in self._menu_items():
            self._page.get_by_text(label).click()

    def create_product(self, album_id: str, fields: dict[str, Any]) -> str:
        """创建产品并读取产品 ID；结果不明确抛 RESULT_UNCERTAIN."""
        self.navigate()
        self._page.locator(self._selectors["product_create_button"]).click()
        self._page.locator(self._selectors["product_carrier"]).fill(
            str(fields.get("carrier") or DEFAULT_CARRIER)
        )
        self._page.locator(self._selectors["product_album_id"]).fill(album_id)
        self._page.locator(self._selectors["product_copyright"]).fill(
            str(fields.get("copyright") or DEFAULT_COPYRIGHT)
        )
        self._page.locator(self._selectors["product_monetization"]).fill(
            str(fields.get("monetization") or DEFAULT_MONETIZATION)
        )
        self._page.locator(self._selectors["product_save_button"]).click()
        self._page.locator(self._selectors["confirm_dialog"]).click()
        product_id = (
            self._page.locator(self._selectors["product_id_field"]).input_value()
            or ""
        ).strip()
        if not product_id:
            raise ExternalAdapterError(
                "巨量产品创建后未读到产品 ID，结果不确定",
                code=RESULT_UNCERTAIN,
            )
        return product_id

    def verify_product(self, product_id: str) -> bool:
        """进入产品库并按产品 ID 匹配行确认存在."""
        self.navigate()
        row = self._page.locator(
            f"{self._selectors['product_row']}:has-text('{product_id}')"
        )
        return row.count() > 0

    def _menu_items(self) -> list[str]:
        menu = self._selectors["product_menu"]
        if isinstance(menu, str):
            return [item.strip() for item in menu.split("→") if item.strip()]
        return list(menu)

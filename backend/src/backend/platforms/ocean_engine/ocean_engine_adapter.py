"""巨量产品库真实 Adapter：Playwright Page Object 封装，dry_run 不操作页面."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.domain.ports.adapters import (
    OceanEngineAdapter as OceanEngineAdapterProtocol,
)
from backend.platforms.ocean_engine.page_objects.product_library_page import (
    ProductLibraryPage,
)


logger = logging.getLogger(__name__)

_DEFAULT_SELECTORS_PATH = (
    Path(__file__).resolve().parents[5]
    / "configs"
    / "defaults"
    / "ocean_engine_selectors.json"
)


def _load_default_selectors() -> dict[str, Any]:
    """加载 configs/defaults/ocean_engine_selectors.json，选择器不写死在代码."""
    with _DEFAULT_SELECTORS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


class OceanEngineAdapter(OceanEngineAdapterProtocol):
    """Playwright 版巨量产品库 Adapter；dry_run=True 只记录调用，不操作 page."""

    def __init__(
        self,
        selectors: dict[str, Any] | None = None,
        page: Any = None,
        dry_run: bool = True,
    ) -> None:
        self._selectors = selectors or _load_default_selectors()
        self._page = page
        self._dry_run = dry_run
        self._recorded_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    @property
    def recorded_calls(self) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        """dry_run 模式下记录但未执行的调用（仅供测试/日志观察）。"""
        return list(self._recorded_calls)

    def create_product(self, album_id: str, fields: dict[str, Any]) -> str:
        """在巨量产品库创建产品并返回产品 ID."""
        self._record("create_product", album_id, fields)
        if self._dry_run:
            return f"prod-{album_id}"
        return ProductLibraryPage(self._page, self._selectors).create_product(
            album_id, fields
        )

    def verify_product(self, product_id: str) -> bool:
        """按产品 ID 校验产品已存在."""
        self._record("verify_product", product_id)
        if self._dry_run:
            return True
        return ProductLibraryPage(self._page, self._selectors).verify_product(
            product_id
        )

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        if not self._dry_run:
            return
        self._recorded_calls.append((name, args, kwargs))
        logger.info("ocean engine adapter 记录调用 dry_run=%s: %s", self._dry_run, name)

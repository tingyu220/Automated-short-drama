"""巨量产品库 Adapter Mock 实现 —— 确定性建产品，无网络."""
from __future__ import annotations

from typing import Any

from backend.domain.ports.adapters import OceanEngineAdapter


class MockOceanEngineAdapter(OceanEngineAdapter):
    """确定性巨量产品库 Mock."""

    def create_product(self, album_id: str, fields: dict[str, Any]) -> str:
        del fields  # Mock 不校验产品字段
        return f"prod-{album_id}"

    def verify_product(self, product_id: str) -> bool:
        del product_id  # Mock 恒为已创建成功
        return True

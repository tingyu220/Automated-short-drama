"""推广链接资产领域模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class AcquisitionMethod:
    """资产获取方式。"""

    API = "API"
    NETWORK = "NETWORK"
    DOM = "DOM"
    MANUAL = "MANUAL"
    LEGACY = "LEGACY"


class AssetStatus:
    """资产采集状态。"""

    DISCOVERED = "DISCOVERED"
    VALIDATED = "VALIDATED"
    AMBIGUOUS = "AMBIGUOUS"
    FAILED = "FAILED"
    EXPECTED_ABSENT = "EXPECTED_ABSENT"
    UNVERIFIED = "UNVERIFIED"


class VerificationStatus:
    """资产验证状态。"""

    UNVERIFIED = "UNVERIFIED"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"


class CreationStatus:
    """资产来源状态。"""

    EXISTING = "EXISTING"
    CREATED = "CREATED"
    UNKNOWN = "UNKNOWN"


@dataclass
class PromotionAsset:
    """一次推广链接发现及其验证事实。"""

    id: str
    task_id: str
    source_platform: str
    drama_name: str
    link_type: str
    promotion_url: str
    external_drama_id: str | None = None
    promotion_id: str | None = None
    episode: int | None = None
    template_id: str | None = None
    template_name: str | None = None
    price: float | None = None
    acquisition_method: str = AcquisitionMethod.LEGACY
    acquisition_status: str = AssetStatus.DISCOVERED
    verification_status: str = VerificationStatus.UNVERIFIED
    created_or_existing: str = CreationStatus.UNKNOWN
    raw_data: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def business_identity(self) -> tuple[str, str, str, str] | None:
        """返回可确定的业务身份；缺少平台剧目 ID 时不猜测去重。"""
        if not self.external_drama_id:
            return None
        if self.link_type == "IAA" and self.episode is not None:
            discriminator = f"episode:{self.episode}"
        elif self.link_type in {"2.9", "9.9", "IAP"} and self.template_id:
            discriminator = f"template:{self.template_id}"
        else:
            return None
        return (
            self.source_platform,
            self.external_drama_id,
            self.link_type,
            discriminator,
        )


"""现有番茄 DOM 链路的兼容 Provider。"""
from __future__ import annotations

import uuid

from backend.application.services.tomato_extraction_service import scan_iap
from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    CreationStatus,
    PromotionAsset,
)
from backend.domain.common.timezones import as_utc
from backend.domain.ports.adapters import PromotionLink, TemplateInfo, TomatoAdapter
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask


class LegacyDomProvider:
    """包装旧 Adapter/Page Object，不在本层改变页面操作行为。"""

    def __init__(
        self,
        tomato: TomatoAdapter,
        price_rules: list[TemplatePriceRule],
    ) -> None:
        self._tomato = tomato
        self._price_rules = price_rules

    def acquire(self, task: DramaTask) -> AcquisitionResult:
        available_time = as_utc(task.available_time)
        confirmation = task.confirmed_drama_match
        if confirmation is None:
            episode_count = self._tomato.get_episode_count(
                task.drama_name,
                available_time,
            )
        else:
            episode_count = self._tomato.get_episode_count(
                task.drama_name,
                available_time,
                confirmation,
            )
        scan = scan_iap(
            task.drama_name,
            available_time,
            self._tomato,
            self._price_rules,
            episode_count=episode_count,
            confirmed_match=confirmation,
        )

        candidates = [
            _asset(
                task,
                scan.iaa_link,
                link_type="IAA",
                episode=2 if episode_count > 50 else 1,
            )
        ]
        expected_types = ["IAA"]
        for link_type, link in (
            ("2.9", scan.iap_2_9_link),
            ("9.9", scan.iap_9_9_link),
        ):
            if link is None or not link.promotion_url:
                continue
            template = _template_for_link_type(
                link_type,
                scan.matched_templates,
            )
            expected_types.append(link_type)
            candidates.append(
                _asset(
                    task,
                    link,
                    link_type=link_type,
                    template=template,
                )
            )

        missing = {
            str(failure.get("link_type") or "IAP"): str(
                failure.get("code") or "LEGACY_ACQUISITION_FAILED"
            )
            for failure in scan.iap_failures
        }
        for link_type in missing:
            if link_type not in expected_types:
                expected_types.append(link_type)

        return AcquisitionResult(
            status=(
                AcquisitionStatus.PARTIAL
                if candidates
                else AcquisitionStatus.NOT_FOUND
            ),
            expected_types=expected_types,
            candidates=candidates,
            missing=missing,
            diagnostics={
                "provider": "LEGACY_DOM",
                "business_result": scan.business_result,
                "iap_failures": list(scan.iap_failures),
                "iap_diag": dict(scan.diag),
            },
        )


def _template_for_link_type(
    link_type: str,
    templates: list[TemplateInfo],
) -> TemplateInfo | None:
    """按目标档位选择模板，避免另一档生成失败导致索引错配。"""
    try:
        target_price = float(link_type)
    except ValueError:
        return None
    if not templates:
        return None
    return min(
        templates,
        key=lambda template: (
            abs(template.price - target_price),
            template.page_order,
        ),
    )



def _asset(
    task: DramaTask,
    link: PromotionLink,
    *,
    link_type: str,
    episode: int | None = None,
    template: TemplateInfo | None = None,
) -> PromotionAsset:
    return PromotionAsset(
        id=str(uuid.uuid4()),
        task_id=task.id,
        source_platform=link.source_platform or task.platform,
        drama_name=link.drama_name,
        link_type=link_type,
        promotion_url=link.promotion_url,
        episode=episode,
        template_id=template.template_id if template else None,
        template_name=template.title if template else None,
        price=template.price if template else None,
        acquisition_method=AcquisitionMethod.LEGACY,
        created_or_existing=(
            CreationStatus.EXISTING
            if link.acquisition_method == "PROMOTION_LIST_VIEW"
            else CreationStatus.UNKNOWN
        ),
        raw_data={
            "source_entry": link.source_entry,
            "legacy_acquisition_method": link.acquisition_method,
            "source_column": link.source_column,
            "url_length": link.url_length,
            "link_status": link.link_status,
        },
    )

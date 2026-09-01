"""验证 Ready Gate 区分 NOT_FOUND（放行）和提取失败（拦截）。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.application.services.link_acquisition_service import (
    LinkAcquisitionService,
)
from backend.application.services.task_preparation_service import (
    MANUAL_REVIEW,
    READY,
    TaskPreparationService,
)
from backend.domain.acquisition.acquisition_result import (
    AcquisitionResult,
    AcquisitionStatus,
)
from backend.domain.assets.promotion_asset import (
    AcquisitionMethod,
    AssetStatus,
    CreationStatus,
    PromotionAsset,
    VerificationStatus,
)
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.mock.mock_tomato import MockTomatoAdapter


class MemoryTaskRepo:
    def __init__(self):
        self.items: dict[str, DramaTask] = {}

    def add(self, task):
        self.items[task.id] = task
        return task

    def get(self, task_id):
        return self.items.get(task_id)

    def update(self, task):
        self.items[task.id] = task
        return task


class MemoryQueueRepo:
    def __init__(self):
        self.items: dict[str, QueueItem] = {}

    def add(self, item):
        self.items[item.id] = item
        return item

    def list_by_task(self, task_id):
        return [item for item in self.items.values() if item.task_id == task_id]


class RecordingFeishu:
    def __init__(self, tasks=None):
        self.tasks = tasks or []
        self.writes = []

    def fetch_tasks(self, day):
        return list(self.tasks)

    def write_links(self, task_id, links):
        self.writes.append((task_id, dict(links)))


class _MemoryPromotionAssetRepo:
    def save_all(self, assets):
        return assets


def _price_rules():
    return [
        TemplatePriceRule(target_price=2.9, min_price=2.0, max_price=5.0, key="iap_2_9"),
        TemplatePriceRule(target_price=9.9, min_price=7.0, max_price=15.0, key="iap_9_9"),
    ]


def _task():
    return DramaTask(
        id="t1",
        sheet_row=1,
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links={},
    )


def _make_asset(link_type, url="aweme://playlet?x=1"):
    return PromotionAsset(
        id=f"a-{link_type}",
        task_id="t1",
        source_platform="TOMATO",
        drama_name="剧A",
        link_type=link_type,
        promotion_url=url,
        promotion_id=f"p-{link_type}",
        external_drama_id="drama-1",
        acquisition_method=AcquisitionMethod.NETWORK,
        acquisition_status=AssetStatus.VALIDATED,
        verification_status=VerificationStatus.VALIDATED,
        created_or_existing=CreationStatus.EXISTING,
    )


class _LinkAcqWrapper:
    """包装 LinkAcquisitionService 以返回指定结果和 acquisition_missing。"""

    def __init__(self, result):
        self._result = result

    def acquire(self, task):
        return self._result

    def build_link_snapshot(self, result):
        return {
            asset.link_type: asset.promotion_url
            for asset in result.selected
            if asset.acquisition_status == AssetStatus.VALIDATED
            and asset.verification_status == VerificationStatus.VALIDATED
            and asset.promotion_url
        }


def _make_service(provider_result):
    return TaskPreparationService(
        RecordingFeishu(),
        MockTomatoAdapter(),
        MemoryTaskRepo(),
        MemoryQueueRepo(),
        price_rules=_price_rules(),
        link_acquisition=_LinkAcqWrapper(provider_result),
    )


class TestReadyGateBlocksFailedIap:
    """Phase 4: Ready Gate 区分 NOT_FOUND 和提取失败。"""

    def test_only_iaa_found_2_9_9_9_not_found_passes(self):
        """IAA 找到，2.9/9.9 在后台不存在（NOT_FOUND）→ 放行。"""
        iaa = _make_asset("IAA")
        result = AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[iaa],
            selected=[iaa],
            missing={"2.9": "NOT_FOUND", "9.9": "NOT_FOUND"},
        )
        service = _make_service(result)
        outcome = service.prepare_task(_task(), dry_run=True)

        assert outcome.status == READY

    def test_only_iaa_found_2_9_ambiguous_blocks(self):
        """IAA 找到，2.9 有歧义（AMBIGUOUS）→ 拦截。"""
        iaa = _make_asset("IAA")
        result = AcquisitionResult(
            status=AcquisitionStatus.AMBIGUOUS,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[iaa],
            selected=[iaa],
            missing={"2.9": "AMBIGUOUS", "9.9": "NOT_FOUND"},
        )
        service = _make_service(result)
        outcome = service.prepare_task(_task(), dry_run=True)

        assert outcome.status == MANUAL_REVIEW

    def test_all_found_passes(self):
        """IAA + 2.9 + 9.9 全部找到 → 放行。"""
        iaa = _make_asset("IAA")
        p29 = _make_asset("2.9", "aweme://playlet?x=2")
        p99 = _make_asset("9.9", "aweme://playlet?x=3")
        result = AcquisitionResult(
            status=AcquisitionStatus.COMPLETE,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[iaa, p29, p99],
            selected=[iaa, p29, p99],
            missing={},
        )
        service = _make_service(result)
        outcome = service.prepare_task(_task(), dry_run=True)

        assert outcome.status == READY

    def test_found_but_not_in_missing_blocks(self):
        """档位不在 links 也不在 missing（有候选但验证失败）→ 拦截。"""
        iaa = _make_asset("IAA")
        result = AcquisitionResult(
            status=AcquisitionStatus.PARTIAL,
            expected_types=["IAA", "2.9", "9.9"],
            candidates=[iaa],
            selected=[iaa],
            missing={"9.9": "NOT_FOUND"},
            # 2.9 is not in missing and not in selected → validation failed
        )
        service = _make_service(result)
        outcome = service.prepare_task(_task(), dry_run=True)

        assert outcome.status == MANUAL_REVIEW

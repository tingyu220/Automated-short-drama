"""任务到点准备：冻结链接、按安全模式回填飞书并维护等待队列。"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from backend.application.services.link_acquisition_service import (
    LinkAcquisitionService,
    NullPromotionAssetRepository,
)
from backend.domain.acquisition.promotion_asset_validator import (
    PromotionAssetValidator,
)
from backend.domain.common.timezones import as_utc
from backend.domain.errors.domain_error import DramaMismatchError
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.domain.tasks.end_type import EndType
from backend.platforms.tomato.providers.legacy_dom_provider import LegacyDomProvider

logger = logging.getLogger(__name__)

READY = "READY"
MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(frozen=True)
class PreparationResult:
    """一轮前置扫描统计。"""

    day: date
    prepared: int
    ready: int
    manual_review: int
    skipped: int


@dataclass(frozen=True)
class PreparationOutcome:
    """单任务准备结果及不可自动重试的失败详情。"""

    status: str
    failure_code: str | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedLinks:
    """冻结链接及不阻断 IAP 提取失败记录。"""

    links: dict[str, str]
    iap_failures: list[dict[str, str]] = field(default_factory=list)
    diag: dict[str, Any] = field(default_factory=dict)
    failure_code: str | None = None


def _build_details(resolved: ResolvedLinks) -> dict[str, Any]:
    """从解析结果构造输出到 step_run 的 detail 字典。"""
    details: dict[str, Any] = {}
    if resolved.iap_failures:
        details["iap_failures"] = resolved.iap_failures
    if resolved.diag:
        details["iap_diag"] = resolved.diag
    return details


class TaskPreparationService:
    """把飞书当天剧目变成已冻结链接的可执行任务。"""

    def __init__(
        self,
        feishu,
        tomato,
        task_repo,
        queue_repo,
        *,
        price_rules,
        youxuan=None,
        promotion_asset_repo=None,
        link_acquisition=None,
    ):
        self._feishu = feishu
        self._tomato = tomato
        self._task_repo = task_repo
        self._queue_repo = queue_repo
        self._price_rules = price_rules
        self._youxuan = youxuan
        self._link_acquisition = link_acquisition or LinkAcquisitionService(
            LegacyDomProvider(tomato, price_rules),
            PromotionAssetValidator(),
            promotion_asset_repo or NullPromotionAssetRepository(),
        )

    def prepare(
        self,
        day: date,
        *,
        dry_run: bool = False,
        now: datetime | None = None,
    ) -> PreparationResult:
        """只准备已到 E 时间的任务；时间未到绝不访问番茄。"""
        current = as_utc(now or datetime.now(timezone.utc))
        sources = sorted(
            self._feishu.fetch_tasks(day),
            key=lambda task: (task.available_time, task.id),
        )
        ready = manual_review = skipped = prepared = 0
        for source in sources:
            if current < as_utc(source.available_time):
                skipped += 1
                continue
            outcome = self.prepare_task(
                source,
                dry_run=dry_run,
                now=current,
            )
            if outcome.status == "READY":
                prepared += 1
                ready += 1
            elif outcome.status == "MANUAL_REVIEW":
                prepared += 1
                manual_review += 1
            else:
                skipped += 1

        return PreparationResult(day, prepared, ready, manual_review, skipped)

    def prepare_task(
        self,
        source: DramaTask,
        *,
        dry_run: bool,
        now: datetime | None = None,
    ) -> PreparationOutcome:
        """准备单个到点任务，返回 READY/MANUAL_REVIEW/SKIPPED。"""
        current = as_utc(now or datetime.now(timezone.utc))
        if current < as_utc(source.available_time):
            return PreparationOutcome("SKIPPED")
        existing = self._task_repo.get(source.id)
        if existing is not None and existing.link_status == "VALIDATED":
            self._ensure_queue(existing)
            return PreparationOutcome("SKIPPED")

        task = existing or source
        task.source_links = dict(source.source_links)
        task.drama_name = source.drama_name
        task.platform = source.platform
        task.end_type = source.end_type
        task.available_time = as_utc(source.available_time)
        try:
            resolved = self._resolve_links(task)
        except DramaMismatchError as exc:
            task.status = TaskStatus.MANUAL_REVIEW
            task.link_status = "DRAMA_MISMATCH"
            self._save(task, existing)
            return PreparationOutcome(
                MANUAL_REVIEW,
                failure_code=exc.code,
                details=dict(exc.details),
            )
        if not resolved.links or (
            source.platform == "TOMATO" and not resolved.links.get("IAA")
        ):
            task.status = TaskStatus.MANUAL_REVIEW
            task.link_status = "FAILED"
            self._save(task, existing)
            return PreparationOutcome(
                MANUAL_REVIEW,
                failure_code=resolved.failure_code or "NO_LINKS",
            )

        link_status = _resolved_link_status(resolved.links)
        task.link_set = resolved.links
        task.confirmed_drama_match = None
        if link_status == "INVALID_URL":
            task.status = TaskStatus.MANUAL_REVIEW
            task.link_status = link_status
            if source.platform == "TOMATO" and not dry_run:
                self._feishu.write_links(_sheet_row_id(source), resolved.links)
            self._save(task, existing)
            return PreparationOutcome(
                MANUAL_REVIEW,
                failure_code="INVALID_URL",
            )
        task.link_status = "VALIDATED"
        task.status = TaskStatus.READY
        if source.platform == "TOMATO" and not dry_run:
            self._feishu.write_links(_sheet_row_id(source), resolved.links)
        self._save(task, existing)
        self._ensure_queue(task)
        return PreparationOutcome(
            READY,
            details=_build_details(resolved),
        )

    def _resolve_links(self, task: DramaTask) -> ResolvedLinks:
        if task.end_type == EndType.MINIPROGRAM:
            return self._resolve_youxuan_links(task)
        if task.platform == "JUBIAN":
            return ResolvedLinks(
                {key: value for key, value in task.source_links.items() if value}
            )
        if task.platform != "TOMATO":
            return ResolvedLinks({})

        acquisition = self._link_acquisition.acquire(task)
        iap_failures = list(
            acquisition.diagnostics.get("iap_failures") or []
        )
        iap_diag = dict(acquisition.diagnostics.get("iap_diag") or {})
        if iap_failures:
            logger.warning(
                "IAP 链接提取失败: task=%s drama=%s failures=%s",
                task.id,
                task.drama_name,
                iap_failures,
            )
        else:
            logger.info(
                "链接采集结果: task=%s drama=%s status=%s selected=%s",
                task.id,
                task.drama_name,
                acquisition.status,
                [asset.link_type for asset in acquisition.selected],
            )
        links = self._link_acquisition.build_link_snapshot(acquisition)
        return ResolvedLinks(
            links,
            iap_failures=iap_failures,
            diag=iap_diag,
            failure_code=_acquisition_failure_code(acquisition),
        )

    def _resolve_youxuan_links(self, task: DramaTask) -> ResolvedLinks:
        """小程序产线：通过 youxuan2 平台提取链接。"""
        if self._youxuan is None:
            return ResolvedLinks({})
        promotion_links = self._youxuan.extract_links(task.drama_name)
        links: dict[str, str] = {}
        for pl in promotion_links:
            if pl.promotion_url:
                links[pl.link_type or "IAA"] = pl.promotion_url
        return ResolvedLinks(links)

    def _save(self, task: DramaTask, existing: DramaTask | None) -> None:
        if existing is None:
            self._task_repo.add(task)
        else:
            self._task_repo.update(task)

    def _ensure_queue(self, task: DramaTask) -> None:
        active = [
            item
            for item in self._queue_repo.list_by_task(task.id)
            if item.state not in {QueueState.COMPLETED, QueueState.CANCELLED}
        ]
        if active:
            return
        self._queue_repo.add(
            QueueItem(
                id=str(uuid.uuid4()),
                task_id=task.id,
                state=QueueState.WAITING_TIME,
                available_at=task.available_time,
            )
        )


def _resolved_link_status(links: dict[str, str]) -> str:
    for url in links.values():
        if _is_mock_url(url):
            continue
        if not _is_valid_aweme_url(url):
            return "INVALID_URL"
    return "VALIDATED"


def _is_valid_aweme_url(url: str) -> bool:
    """校验 aweme:// 协议 URL 带查询参数。"""
    if not url.startswith("aweme://"):
        return False
    if "?" not in url:
        return False
    query = url.split("?", 1)[1]
    return "=" in query


def _acquisition_failure_code(acquisition) -> str | None:
    if acquisition.status == "AMBIGUOUS":
        return "LINK_ASSET_AMBIGUOUS"
    if acquisition.candidates and not acquisition.selected:
        return "LINK_VALIDATION_FAILED"
    if not acquisition.candidates:
        return "LINK_ASSET_NOT_FOUND"
    return None


def _is_mock_url(url: str) -> bool:
    return url.startswith("mock://")


def _sheet_row_id(task: DramaTask) -> str:
    return str(task.sheet_row) if task.sheet_row is not None else task.id

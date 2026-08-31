"""链接准备阶段编排：提链、剧目资源、推广内容。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.domain.common.timezones import as_utc
from backend.domain.errors.domain_error import DomainError
from backend.domain.ports.adapters import DramaAsset
from backend.domain.tasks.drama_task import DramaTask
from backend.domain.tasks.end_type import EndType
from backend.domain.workflow.link_stage import LinkStage, RunTarget


@dataclass(frozen=True)
class LinkReadinessOutcome:
    """一次阶段执行的业务结果。"""

    status: str
    task: DramaTask
    failure_code: str | None = None
    details: dict = field(default_factory=dict)


class LinkReadinessService:
    """按指定终点幂等推进链接准备。"""

    def __init__(
        self,
        preparation,
        delivery_flow,
        task_repo,
        workflow_repo,
    ) -> None:
        self._preparation = preparation
        self._delivery = delivery_flow
        self._task_repo = task_repo
        self._workflow_repo = workflow_repo

    def execute(
        self,
        task: DramaTask,
        target_stage: str,
        *,
        dry_run: bool,
        now: datetime,
    ) -> LinkReadinessOutcome:
        target = RunTarget.validate(target_stage)
        task.target_stage = target
        if as_utc(now) < as_utc(task.available_time):
            task.current_stage = LinkStage.WAITING_AVAILABLE_TIME
            self._task_repo.update(task)
            return LinkReadinessOutcome(LinkStage.WAITING_AVAILABLE_TIME, task)

        link_result = self._ensure_links(task, dry_run=dry_run, now=now)
        if link_result.status == "MANUAL_REVIEW":
            return link_result
        link_details = dict(link_result.details)
        if target == RunTarget.LINK_EXTRACTION:
            task.status = "LINK_EXTRACTED"
            self._task_repo.update(task)
            return LinkReadinessOutcome(
                "LINK_EXTRACTED", task, details=link_details
            )

        if task.end_type == EndType.MINIPROGRAM:
            task.current_stage = LinkStage.LINK_READY
            task.status = LinkStage.LINK_READY
            self._task_repo.update(task)
            return LinkReadinessOutcome(
                LinkStage.LINK_READY, task, details=link_details
            )

        asset_error = self._ensure_delivery_drama(task)
        if asset_error is not None:
            return asset_error
        config_error = self._ensure_promotion_configs(task)
        if config_error is not None:
            return config_error

        task.current_stage = LinkStage.LINK_READY
        task.status = LinkStage.LINK_READY
        self._task_repo.update(task)
        return LinkReadinessOutcome(
            LinkStage.LINK_READY, task, details=link_details
        )

    def _ensure_links(
        self, task: DramaTask, *, dry_run: bool, now: datetime
    ) -> LinkReadinessOutcome:
        if task.link_status == "VALIDATED" and task.link_set:
            task.current_stage = LinkStage.LINK_EXTRACTION
            self._task_repo.update(task)
            return LinkReadinessOutcome("READY", task)
        step = self._workflow_repo.start_step(
            task.id, LinkStage.LINK_EXTRACTION
        )
        try:
            outcome = self._preparation.prepare_task(
                task, dry_run=dry_run, now=now
            )
            if outcome.status != "READY":
                code = outcome.failure_code or outcome.status
                message = f"链接提取未完成: {code}"
                self._workflow_repo.fail_step(step, code, message)
                task.current_stage = LinkStage.LINK_EXTRACTION
                task.status = "MANUAL_REVIEW"
                self._task_repo.update(task)
                return LinkReadinessOutcome(
                    "MANUAL_REVIEW",
                    task,
                    failure_code=code,
                    details=dict(outcome.details),
                )
            persisted = self._task_repo.get(task.id)
            if persisted is None:
                raise ValueError(f"任务 {task.id} 在链接提取后不存在")
            task.link_set = dict(persisted.link_set)
            task.source_links = dict(persisted.source_links)
            task.link_status = persisted.link_status
            task.status = persisted.status
            task.current_stage = LinkStage.LINK_EXTRACTION
            self._task_repo.update(task)
            details = dict(outcome.details)
            self._workflow_repo.finish_step(
                step, {"links": dict(task.link_set), **details}
            )
            return LinkReadinessOutcome("READY", task, details=details)
        except Exception as exc:
            return self._stage_failure(task, step, LinkStage.LINK_EXTRACTION, exc)

    def _ensure_delivery_drama(
        self, task: DramaTask
    ) -> LinkReadinessOutcome | None:
        if task.delivery_drama_id:
            task.current_stage = LinkStage.DELIVERY_DRAMA
            self._task_repo.update(task)
            return None
        step = self._workflow_repo.start_step(
            task.id, LinkStage.DELIVERY_DRAMA
        )
        try:
            asset = self._delivery.ensure_drama_asset(
                task.drama_name, _primary_link(task.link_set)
            )
            task.delivery_drama_id = asset.delivery_drama_id
            task.current_stage = LinkStage.DELIVERY_DRAMA
            self._task_repo.update(task)
            self._workflow_repo.finish_step(
                step,
                {
                    "delivery_drama_id": asset.delivery_drama_id,
                    "album_id": asset.album_id,
                },
            )
            return None
        except Exception as exc:
            return self._stage_failure(task, step, LinkStage.DELIVERY_DRAMA, exc)

    def _ensure_promotion_configs(
        self, task: DramaTask
    ) -> LinkReadinessOutcome | None:
        missing = [
            (link_type, link)
            for link_type, link in task.link_set.items()
            if link and not task.promotion_configs.get(link_type)
        ]
        if not missing:
            task.current_stage = LinkStage.PROMOTION_CONFIG
            self._task_repo.update(task)
            return None
        step = self._workflow_repo.start_step(
            task.id, LinkStage.PROMOTION_CONFIG
        )
        asset = DramaAsset(
            delivery_drama_id=task.delivery_drama_id,
            drama_name=task.drama_name,
            link=_primary_link(task.link_set),
        )
        try:
            for link_type, link in missing:
                task.promotion_configs[link_type] = (
                    self._delivery.ensure_promotion_config(
                        asset, link_type, link, task.platform
                    )
                )
                self._task_repo.update(task)
            task.current_stage = LinkStage.PROMOTION_CONFIG
            self._task_repo.update(task)
            self._workflow_repo.finish_step(
                step, {"promotion_configs": dict(task.promotion_configs)}
            )
            return None
        except Exception as exc:
            return self._stage_failure(
                task, step, LinkStage.PROMOTION_CONFIG, exc
            )

    def _stage_failure(
        self, task: DramaTask, step, stage: str, error: Exception
    ) -> LinkReadinessOutcome:
        code = error.code if isinstance(error, DomainError) else type(error).__name__
        self._workflow_repo.fail_step(step, code, str(error))
        task.current_stage = stage
        task.status = "MANUAL_REVIEW"
        self._task_repo.update(task)
        details = dict(error.details) if isinstance(error, DomainError) else {}
        return LinkReadinessOutcome(
            "MANUAL_REVIEW",
            task,
            failure_code=code,
            details=details,
        )


def _primary_link(links: dict[str, str]) -> str:
    for link_type in ("IAA", "2.9", "9.9"):
        if links.get(link_type):
            return links[link_type]
    raise ValueError("任务没有可用于创建投放剧目的链接")

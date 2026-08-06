"""标准投放执行服务：校验 → M=1 闸门 → 资源/产品/提交/轮询 → 台账。

只有投放任务状态达到 COMPLETED 才允许写 M=1 与成功台账；
校验失败、提交被安全开关拦截、超时、部分失败或异常一律不写。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.application.services.delivery_flow_service import DeliveryFlowService
from backend.application.services.plan_validation_service import ValidationIssue
from backend.domain.errors.domain_error import NotFoundError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import (
    DeliverySystemAdapter,
    FeishuAdapter,
    OceanEngineAdapter,
)
from backend.domain.ports.repositories import LedgerRepository, TaskRepository

VALIDATION_FAILED = "VALIDATION_FAILED"
DRY_RUN = "DRY_RUN"
COMPLETED = "COMPLETED"
MANUAL_REVIEW = "MANUAL_REVIEW"

# 轮询最长 24 次；测试环境间隔为 0，真实环境由调度层决定。
_MAX_POLLS = 24
_POLL_INTERVAL_SECONDS = 0


@dataclass
class DeliveryOutcome:
    """一次标准投放执行的最终结果。"""

    status: str
    external_task_id: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    ledger_id: str | None = None


class StandardDeliveryService:
    """编排标准投放执行并守住 M=1 写入门槛。"""

    def __init__(
        self,
        validation,
        delivery: DeliverySystemAdapter,
        ocean: OceanEngineAdapter,
        submit_guard,
        feishu: FeishuAdapter,
        ledger_repo: LedgerRepository,
        task_repo: TaskRepository,
    ) -> None:
        self._validation = validation
        self._delivery_flow = DeliveryFlowService(delivery, ocean)
        self._submit_guard = submit_guard
        self._feishu = feishu
        self._ledger_repo = ledger_repo
        self._task_repo = task_repo

    def execute(
        self,
        plan_spec: PlanSpec,
        cid_configs: list[dict],
        task_id: str,
        allow_final_submit: bool,
        use_real_adapters: bool,
        worker_id: str,
    ) -> DeliveryOutcome:
        """执行标准投放，返回 COMPLETED / DRY_RUN / MANUAL_REVIEW / VALIDATION_FAILED。"""
        report = self._validation.validate(plan_spec, cid_configs)
        if not report.passed:
            return DeliveryOutcome(
                status=VALIDATION_FAILED,
                issues=list(report.issues),
            )

        decision = self._submit_guard.can_submit(
            allow_final_submit, use_real_adapters
        )
        if not decision.allowed:
            return DeliveryOutcome(status=DRY_RUN)

        external_task_id: str | None = None
        try:
            asset = self._delivery_flow.ensure_drama_asset(
                plan_spec.drama_name, next(iter(plan_spec.link_set.values()))
            )
            for link_type, link in plan_spec.link_set.items():
                self._delivery_flow.ensure_promotion_config(
                    asset, link_type, link, plan_spec.platform
                )
            product_id = self._delivery_flow.create_product(
                asset.album_id,
                {
                    "drama_name": plan_spec.drama_name,
                    "album_id": asset.album_id,
                    "link": asset.link,
                },
            )
            external_task_id = self._delivery_flow.submit_plan(plan_spec)
            status = self._delivery_flow.poll_until_completed(
                external_task_id,
                max_polls=_MAX_POLLS,
                interval_seconds=_POLL_INTERVAL_SECONDS,
            )
            if status != COMPLETED:
                return DeliveryOutcome(
                    status=MANUAL_REVIEW,
                    external_task_id=external_task_id,
                )
            return self._finalize_completed(
                plan_spec, task_id, external_task_id, product_id
            )
        except Exception:
            return DeliveryOutcome(
                status=MANUAL_REVIEW,
                external_task_id=external_task_id,
            )

    def _finalize_completed(
        self,
        plan_spec: PlanSpec,
        task_id: str,
        external_task_id: str,
        product_id: str,
    ) -> DeliveryOutcome:
        """平台确认完成后写 M=1 与成功台账。"""
        self._feishu.write_completion(task_id)

        task = self._task_repo.get(task_id)
        if task is None:
            raise NotFoundError(f"DramaTask {task_id} not found")

        now = datetime.now(timezone.utc)
        ledger = TaskLedger(
            id=str(uuid.uuid4()),
            task_id=task_id,
            drama_name=task.drama_name,
            platform=task.platform,
            product_id=product_id,
            external_task_id=external_task_id,
            task_name=plan_spec.task_name,
            final_status=COMPLETED,
            rule_version=plan_spec.rule_version or "",
            completed_at=now,
        )
        saved = self._ledger_repo.add(ledger)
        return DeliveryOutcome(
            status=COMPLETED,
            external_task_id=external_task_id,
            ledger_id=saved.id,
        )

"""标准投放执行服务：校验 → M=1 闸门 → 资源/产品/提交/轮询 → 台账。

只有投放任务状态达到 COMPLETED 才允许写 M=1 与成功台账；
校验失败、提交被安全开关拦截、超时、部分失败或异常一律不写。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.application.services.delivery_flow_service import DeliveryFlowService
from backend.application.services.plan_validation_service import ValidationIssue
from backend.domain.errors.domain_error import (
    ExternalAdapterError,
    NotFoundError,
    ValidationError,
)
from backend.domain.plans.delivery_form_spec import build_delivery_form_spec
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import (
    DeliverySystemAdapter,
    FeishuAdapter,
    OceanEngineAdapter,
)
from backend.domain.ports.repositories import LedgerRepository, TaskRepository
from backend.infrastructure.config.settings import Settings

VALIDATION_FAILED = "VALIDATION_FAILED"
DRY_RUN = "DRY_RUN"
COMPLETED = "COMPLETED"
MANUAL_REVIEW = "MANUAL_REVIEW"

# 轮询最长 24 次；间隔由构造参数控制，默认 0 保持测试兼容。
_MAX_POLLS = 24

logger = logging.getLogger(__name__)


@dataclass
class DeliveryOutcome:
    """一次标准投放执行的最终结果。"""

    status: str
    external_task_id: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    ledger_id: str | None = None
    failure_code: str | None = None
    retry_safe: bool = False


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
        *,
        allow_final_submit: bool | None = None,
        use_real_adapters: bool | None = None,
        poll_interval_seconds: int = 0,
        poll_timeout_seconds: int = 7200,
        on_poll_wait=None,
    ) -> None:
        settings = Settings()
        self._validation = validation
        # 商品库由投放系统自动配置；保留 ocean 参数兼容现有装配，不再调用。
        self._delivery_flow = DeliveryFlowService(delivery, ocean)
        self._submit_guard = submit_guard
        self._feishu = feishu
        self._ledger_repo = ledger_repo
        self._task_repo = task_repo
        self._allow_final_submit = (
            settings.allow_final_submit
            if allow_final_submit is None
            else allow_final_submit
        )
        self._use_real_adapters = (
            False if use_real_adapters is None else use_real_adapters
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_timeout_seconds = poll_timeout_seconds
        self._on_poll_wait = on_poll_wait

    def execute(
        self,
        plan_spec: PlanSpec,
        cid_configs: list[dict],
        task_id: str,
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
            self._allow_final_submit, self._use_real_adapters
        )
        if not decision.allowed:
            return DeliveryOutcome(
                status=DRY_RUN,
                issues=[
                    ValidationIssue(
                        code=decision.reason or "SUBMIT_BLOCKED",
                        message=f"提交被安全开关拦截: {decision.reason}",
                        field="submit_guard",
                    )
                ],
            )

        try:
            delivery_form = build_delivery_form_spec(plan_spec, cid_configs)
        except ValidationError as exc:
            return DeliveryOutcome(
                status=VALIDATION_FAILED,
                issues=[
                    ValidationIssue(
                        code="DELIVERY_FORM_INVALID",
                        message=str(exc),
                        field="delivery_form",
                    )
                ],
            )

        external_task_id: str | None = None
        try:
            asset = self._delivery_flow.ensure_drama_asset(
                plan_spec.drama_name, next(iter(plan_spec.link_set.values()))
            )
            for link_type, link in plan_spec.link_set.items():
                self._delivery_flow.ensure_promotion_config(
                    asset, link_type, link, plan_spec.platform
                )
            try:
                external_task_id = self._delivery_flow.submit_plan(delivery_form)
            except ExternalAdapterError as exc:
                if exc.code != "RESULT_UNCERTAIN":
                    raise
                external_task_id = self._delivery_flow.find_task_by_idempotency_key(
                    plan_spec.task_name
                )
                if external_task_id is None:
                    return DeliveryOutcome(
                        status=MANUAL_REVIEW,
                        failure_code="RESULT_UNCERTAIN",
                        retry_safe=True,
                    )
            if self._poll_interval_seconds > 0:
                status = self._delivery_flow.poll_until_completed(
                    external_task_id,
                    poll_interval_seconds=self._poll_interval_seconds,
                    timeout_seconds=self._poll_timeout_seconds,
                    on_wait=self._on_poll_wait,
                )
            else:
                status = self._delivery_flow.poll_until_completed(
                    external_task_id,
                    max_polls=_MAX_POLLS,
                )
            if status != COMPLETED:
                return DeliveryOutcome(
                    status=MANUAL_REVIEW,
                    external_task_id=external_task_id,
                )
            return self._finalize_completed(
                plan_spec, task_id, external_task_id, ""
            )
        except ExternalAdapterError as exc:
            logger.exception(
                "标准投放外部操作失败: task_id=%s external_task_id=%s code=%s",
                task_id,
                external_task_id,
                exc.code,
            )
            return DeliveryOutcome(
                status=MANUAL_REVIEW,
                external_task_id=external_task_id,
                failure_code=exc.code,
                retry_safe=False,
            )
        except Exception:
            logger.exception(
                "标准投放执行失败: task_id=%s external_task_id=%s",
                task_id,
                external_task_id,
            )
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
        """平台确认完成后先落成功台账，再写 M=1，避免台账失败留下 M。"""
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
        try:
            self._feishu.write_completion(
                str(task.sheet_row) if task.sheet_row is not None else task_id
            )
        except Exception:
            logger.exception(
                "M=1 写入失败，台账标记 FAILED: task_id=%s ledger_id=%s",
                task_id,
                saved.id,
            )
            saved.final_status = "FAILED"
            self._ledger_repo.update(saved)
            return DeliveryOutcome(
                status=MANUAL_REVIEW,
                external_task_id=external_task_id,
                ledger_id=saved.id,
            )
        return DeliveryOutcome(
            status=COMPLETED,
            external_task_id=external_task_id,
            ledger_id=saved.id,
        )

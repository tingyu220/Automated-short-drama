"""生产验证阶梯执行器：逐级构建 PlanSpec、校验并执行标准投放。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.tasks.drama_task import DramaTask

COMPLETED = "COMPLETED"
VALIDATION_FAILED = "VALIDATION_FAILED"
ERROR = "ERROR"

logger = logging.getLogger(__name__)


@dataclass
class ProductionStep:
    """一级生产验证：一份剧本及其执行参数。"""

    step_name: str
    drama_name: str
    plan_type: str = "test"
    platform: str = "TOMATO"
    links: dict[str, str] = field(default_factory=dict)
    accounts: list[dict] = field(default_factory=list)
    cid_configs: list[dict] = field(default_factory=list)
    product_id: str | None = None
    material_count: int = 3
    material_ranges: list[MaterialRuleRange] = field(default_factory=list)
    rule_version: str | None = None
    include_test: bool = False
    task_id: str = ""
    allow_final_submit: bool = False
    use_real_adapters: bool = False
    worker_id: str = "production-validation"


@dataclass
class LadderStepResult:
    """单级阶梯执行结果。"""

    step_name: str
    drama_name: str
    plan_type: str
    status: str
    external_task_id: str | None = None
    ledger_id: str | None = None
    passed: bool = False


class ProductionValidationRunner:
    """逐级运行生产验证阶梯，单步失败不阻断后续。"""

    def __init__(
        self,
        plan_builder,
        validation,
        delivery_service,
        adapters,
    ) -> None:
        self._plan_builder = plan_builder
        self._validation = validation
        self._delivery_service = delivery_service
        self._adapters = adapters

    def run_ladder(
        self,
        steps: list[ProductionStep],
    ) -> list[LadderStepResult]:
        """逐级执行并返回每级结果；单级失败/异常只记录，不中断阶梯。"""
        return [self._run_step(step) for step in steps]

    def _run_step(self, step: ProductionStep) -> LadderStepResult:
        result = LadderStepResult(
            step_name=step.step_name,
            drama_name=step.drama_name,
            plan_type=step.plan_type,
            status=ERROR,
        )
        try:
            spec = self._build_spec(step)
            report = self._validation.validate(spec, step.cid_configs)
            if not report.passed:
                result.status = VALIDATION_FAILED
                return result

            outcome = self._delivery_service.execute(
                plan_spec=spec,
                cid_configs=step.cid_configs,
                task_id=step.task_id or step.step_name,
                allow_final_submit=step.allow_final_submit,
                use_real_adapters=step.use_real_adapters,
                worker_id=step.worker_id,
            )
            result.status = outcome.status
            result.external_task_id = outcome.external_task_id
            result.ledger_id = outcome.ledger_id
            result.passed = outcome.status == COMPLETED
            return result
        except Exception:
            logger.exception("生产验证阶梯执行异常: step=%s", step.step_name)
            return result

    def _build_spec(self, step: ProductionStep) -> PlanSpec:
        task = DramaTask(
            id=step.task_id or step.step_name,
            drama_name=step.drama_name,
            platform=step.platform,
            available_time=datetime.now(timezone.utc),
        )
        return self._plan_builder.build(
            task,
            step.links,
            step.accounts,
            step.product_id,
            step.material_count,
            step.material_ranges,
            step.rule_version,
            include_test=step.include_test,
        )

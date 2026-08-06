"""完整 Dry Run 工作流：番茄/剧变链接提取到投放提交与轮询编排.

Dry Run 只使用 Mock/内存适配器，不写飞书表、不写 M=1。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from backend.application.services.delivery_flow_service import DeliveryFlowService
from backend.application.services.submit_guard import SubmitDecision, can_submit
from backend.application.services.tomato_extraction_service import extract_iaa, scan_iap
from backend.domain.errors.domain_error import DomainError, ValidationError
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import (
    DeliverySystemAdapter,
    DramaAsset,
    OceanEngineAdapter,
    TomatoAdapter,
)
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.domain.tasks.drama_task import DramaTask

COMPLETED = "COMPLETED"
MANUAL_REVIEW = "MANUAL_REVIEW"
DRY_RUN = "DRY_RUN"
STEP_OK = "OK"
STEP_FAILED = "FAILED"
STEP_SKIPPED = "SKIPPED"

_LINK_TYPES = ("IAA", "2.9", "9.9")
_STEP_LINK_EXTRACTION = "LINK_EXTRACTION"
_STEP_DRAMA_ASSET = "DRAMA_ASSET"
_STEP_PROMOTION_CONFIG = "PROMOTION_CONFIG"
_STEP_PRODUCT = "PRODUCT"
_STEP_PLAN_SPEC = "PLAN_SPEC"
_STEP_SUBMIT = "SUBMIT"
_STEP_POLL = "POLL"


@dataclass
class WorkflowStepResult:
    """单个 Dry Run 步骤结果."""

    step: str
    status: str
    detail: str
    error_code: str = ""


@dataclass
class DryRunResult:
    """一次 Dry Run 的完整结果."""

    task_id: str
    drama_name: str
    platform: str
    final_status: str
    steps: list[WorkflowStepResult] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    asset: DramaAsset | None = None
    plan_spec: PlanSpec | None = None
    external_task_id: str = ""


class DryRunWorkflow:
    """按主流程顺序编排链接、资源、产品、PlanSpec 与提交轮询。"""

    def __init__(
        self,
        tomato: TomatoAdapter,
        delivery: DeliverySystemAdapter,
        ocean: OceanEngineAdapter,
        price_rules: list[TemplatePriceRule],
        *,
        submit_guard: Callable[[bool, bool], SubmitDecision] = can_submit,
        allow_final_submit: bool = False,
        use_real_adapters: bool = False,
    ) -> None:
        self._tomato = tomato
        self._delivery_flow = DeliveryFlowService(delivery, ocean)
        self._price_rules = price_rules
        self._submit_guard = submit_guard
        self._allow_final_submit = allow_final_submit
        self._use_real_adapters = use_real_adapters

    def run(
        self,
        task: DramaTask,
        episode_count: int,
        account_cids: list[str],
        jubian_links: dict[str, str | None] | None = None,
    ) -> DryRunResult:
        """执行完整 Dry Run，任一失败即 MANUAL_REVIEW 且不再继续。"""
        result = DryRunResult(
            task_id=task.id,
            drama_name=task.drama_name,
            platform=task.platform,
            final_status=MANUAL_REVIEW,
        )

        links = self._extract_links_or_fail(result, task, episode_count, jubian_links)
        if links is None:
            return result

        first_link = next(links[t] for t in _LINK_TYPES if t in links)
        asset = self._ensure_asset_or_fail(result, task.drama_name, first_link)
        if asset is None:
            return result

        if not self._ensure_configs_or_fail(result, asset, links, task.platform):
            return result

        product_id = self._create_product_or_fail(result, asset, task.drama_name)
        if product_id is None:
            return result

        plan_spec = self._build_plan_spec_or_fail(
            result, task, links, account_cids, product_id
        )
        if plan_spec is None:
            return result

        external_task_id = self._submit_or_fail(result, plan_spec)
        if external_task_id is None:
            return result

        if not self._poll_or_fail(result, external_task_id):
            return result

        result.external_task_id = external_task_id
        result.final_status = COMPLETED
        return result

    def _extract_links_or_fail(
        self,
        result: DryRunResult,
        task: DramaTask,
        episode_count: int,
        jubian_links: dict[str, str | None] | None,
    ) -> dict[str, str] | None:
        try:
            links = self._extract_links(task, episode_count, jubian_links)
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_LINK_EXTRACTION,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return None

        result.links = links
        if not links:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_LINK_EXTRACTION,
                    status=STEP_FAILED,
                    detail="未获取到任何可用推广链接",
                    error_code="NO_LINKS",
                )
            )
            return None

        result.steps.append(
            WorkflowStepResult(
                step=_STEP_LINK_EXTRACTION,
                status=STEP_OK,
                detail=f"获取到 {len(links)} 条推广链接",
            )
        )
        return links

    def _extract_links(
        self,
        task: DramaTask,
        episode_count: int,
        jubian_links: dict[str, str | None] | None,
    ) -> dict[str, str]:
        if task.platform == "TOMATO":
            return self._extract_tomato_links(task.drama_name, episode_count)
        if task.platform == "JUBIAN":
            return self._extract_jubian_links(jubian_links)
        raise ValidationError(f"不支持的平台: {task.platform}")

    def _extract_tomato_links(
        self, drama_name: str, episode_count: int
    ) -> dict[str, str]:
        """番茄：按集数提取 IAA，再扫描 IAP 模板生成 2.9/9.9 链接。"""
        iaa_link = extract_iaa(drama_name, episode_count, self._tomato)
        scan_result = scan_iap(drama_name, self._tomato, self._price_rules)
        links = {"IAA": iaa_link.promotion_url}
        if scan_result.iap_2_9_link is not None:
            links["2.9"] = scan_result.iap_2_9_link.promotion_url
        if scan_result.iap_9_9_link is not None:
            links["9.9"] = scan_result.iap_9_9_link.promotion_url
        return links

    @staticmethod
    def _extract_jubian_links(
        jubian_links: dict[str, str | None] | None,
    ) -> dict[str, str]:
        """剧变：直接使用表内已有链接，缺失或空值视为不存在。"""
        raw = jubian_links or {}
        return {
            link_type: url
            for link_type in _LINK_TYPES
            if (url := raw.get(link_type))
        }

    def _ensure_asset_or_fail(
        self,
        result: DryRunResult,
        drama_name: str,
        first_link: str,
    ) -> DramaAsset | None:
        try:
            asset = self._delivery_flow.ensure_drama_asset(drama_name, first_link)
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_DRAMA_ASSET,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return None
        result.asset = asset
        result.steps.append(
            WorkflowStepResult(
                step=_STEP_DRAMA_ASSET,
                status=STEP_OK,
                detail=f"剧目资源已就绪: {asset.delivery_drama_id}",
            )
        )
        return asset

    def _ensure_configs_or_fail(
        self,
        result: DryRunResult,
        asset: DramaAsset,
        links: dict[str, str],
        platform: str,
    ) -> bool:
        try:
            for link_type in _LINK_TYPES:
                if link_type in links:
                    self._delivery_flow.ensure_promotion_config(
                        asset, link_type, links[link_type], platform
                    )
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_PROMOTION_CONFIG,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return False
        result.steps.append(
            WorkflowStepResult(
                step=_STEP_PROMOTION_CONFIG,
                status=STEP_OK,
                detail=f"已配置 {len(links)} 条推广内容",
            )
        )
        return True

    def _create_product_or_fail(
        self,
        result: DryRunResult,
        asset: DramaAsset,
        drama_name: str,
    ) -> str | None:
        try:
            product_id = self._delivery_flow.create_product(
                asset.album_id,
                {
                    "drama_name": drama_name,
                    "album_id": asset.album_id,
                    "link": asset.link,
                },
            )
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_PRODUCT,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return None
        result.steps.append(
            WorkflowStepResult(
                step=_STEP_PRODUCT,
                status=STEP_OK,
                detail=f"巨量产品已就绪: {product_id}",
            )
        )
        return product_id

    def _build_plan_spec_or_fail(
        self,
        result: DryRunResult,
        task: DramaTask,
        links: dict[str, str],
        account_cids: list[str],
        product_id: str,
    ) -> PlanSpec | None:
        try:
            plan_spec = PlanSpec(
                drama_name=task.drama_name,
                platform=task.platform,
                task_name=f"DRY-{task.platform}-{task.drama_name}",
                link_set=dict(links),
                account_cids=list(account_cids),
                product_id=product_id,
            )
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_PLAN_SPEC,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return None
        result.plan_spec = plan_spec
        result.steps.append(
            WorkflowStepResult(
                step=_STEP_PLAN_SPEC,
                status=STEP_OK,
                detail=f"PlanSpec 已生成: {plan_spec.task_name}",
            )
        )
        return plan_spec

    def _submit_or_fail(
        self,
        result: DryRunResult,
        plan_spec: PlanSpec,
    ) -> str | None:
        decision = self._submit_guard(
            self._allow_final_submit, self._use_real_adapters
        )
        if not decision.allowed:
            result.final_status = DRY_RUN
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_SUBMIT,
                    status=STEP_SKIPPED,
                    detail=f"提交被安全开关拦截: {decision.reason}",
                )
            )
            return None
        try:
            external_task_id = self._delivery_flow.submit_plan(plan_spec)
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_SUBMIT,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return None
        result.external_task_id = external_task_id
        result.steps.append(
            WorkflowStepResult(
                step=_STEP_SUBMIT,
                status=STEP_OK,
                detail=f"已提交 Dry Run 计划: {external_task_id}",
            )
        )
        return external_task_id

    def _poll_or_fail(
        self,
        result: DryRunResult,
        external_task_id: str,
    ) -> bool:
        try:
            status = self._delivery_flow.poll_until_completed(
                external_task_id, max_polls=24, interval_seconds=0
            )
        except Exception as exc:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_POLL,
                    status=STEP_FAILED,
                    detail=_error_detail(exc),
                    error_code=_error_code(exc),
                )
            )
            return False
        if status != COMPLETED:
            result.steps.append(
                WorkflowStepResult(
                    step=_STEP_POLL,
                    status=STEP_FAILED,
                    detail=f"轮询未完成: {status}",
                    error_code="POLL_TIMEOUT",
                )
            )
            return False
        result.steps.append(
            WorkflowStepResult(
                step=_STEP_POLL,
                status=STEP_OK,
                detail="轮询完成",
            )
        )
        return True


def _error_code(exc: Exception) -> str:
    """统一异常错误码：领域错误保留自身 code，其余按外部适配器错误处理。"""
    return exc.code if isinstance(exc, DomainError) else "EXTERNAL_ADAPTER_ERROR"


def _error_detail(exc: Exception) -> str:
    """异常详情兜底文案。"""
    return str(exc) or "步骤执行失败"

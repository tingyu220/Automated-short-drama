"""Worker 真实编排执行器：链接提取 → 账户分配 → 标准投放。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from backend.application.services import submit_guard
from backend.application.services.account_allocation_service import (
    AccountAllocationService,
)
from backend.application.services.account_assignment_service import (
    AccountAssignmentService,
    AssignmentStatus,
)
from backend.application.services.delivery_config_service import (
    DeliveryConfigSnapshotService,
)
from backend.application.services.delivery_flow_service import DeliveryFlowService
from backend.application.services.link_readiness_service import LinkReadinessService
from backend.application.services.plan_rules import (
    AccountRoutingRule,
    MaterialGroupRule,
    PromotionContentMappingRule,
    TaskNameRule,
)
from backend.application.services.plan_spec_service import PlanSpecBuilder
from backend.application.services.plan_validation_service import PlanValidationService
from backend.application.services.standard_delivery_service import (
    COMPLETED as DELIVERY_COMPLETED,
    DRY_RUN as DELIVERY_DRY_RUN,
    StandardDeliveryService,
)
from backend.application.services.task_preparation_service import (
    READY as PREPARATION_READY,
    PreparationOutcome,
    TaskPreparationService,
)
from backend.application.services.worker_execution import (
    ExecutionOutcome,
    STATUS_COMPLETED,
    STATUS_DRY_RUN,
    STATUS_MANUAL_REVIEW,
    STATUS_LINK_EXTRACTED,
    STATUS_LINK_READY,
)
from backend.domain.execution.execution_event import EventLevel, ExecutionEvent
from backend.domain.common.timezones import SHANGHAI_TZ, as_utc
from backend.domain.errors.domain_error import ValidationError
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.queue.queue_item import QueueItem
from backend.domain.rules.account_block import AccountRow
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
)
from backend.infrastructure.database.repositories.queue_repository import (
    SqlAlchemyQueueRepository,
)
from backend.infrastructure.database.repositories.account_usage_repository import (
    SqlAlchemyAccountUsageRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.infrastructure.database.repositories.promotion_asset_repository import (
    SqlAlchemyPromotionAssetRepository,
)
from backend.infrastructure.database.repositories.workflow_repository import (
    SqlAlchemyWorkflowRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.bootstrap.adapters import AdapterBundle
    from backend.infrastructure.config.settings import Settings

DEFAULT_EPISODE_COUNT = 1
DEFAULT_MATERIAL_COUNT = 3
WORKER_RULE_VERSION = "worker-v1"
CONFIG_VERSION = "1.0"
SUBJECT = "微智造"
ROLE_DELIVERY_TYPES = {
    "B1": "IAA",
    "B4": "IAA",
    "B7": "IAA",
    "BX": "IAA",
    "B1-9.9": "B1-9.9",
    "B2-2.9": "B2-2.9",
}


class _ScratchLedgerRepository:
    """StandardDeliveryService 使用的内存台账仓，避免与 Worker 完成台账重复写库。"""

    def __init__(self) -> None:
        self._ledgers: dict[str, TaskLedger] = {}

    def add(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def get(self, ledger_id: str) -> TaskLedger | None:
        return self._ledgers.get(ledger_id)

    def update(self, ledger: TaskLedger) -> TaskLedger:
        self._ledgers[ledger.id] = ledger
        return ledger

    def list_by_task(self, task_id: str) -> list[TaskLedger]:
        return [l for l in self._ledgers.values() if l.task_id == task_id]

    def list_all(self) -> list[TaskLedger]:
        return list(self._ledgers.values())


def build_link_readiness_executor(
    settings: Settings,
    bundle: AdapterBundle,
    session: Session,
    *,
    use_real_adapters: bool = False,
    on_poll_wait=None,
) -> Callable[[DramaTask, QueueItem], ExecutionOutcome]:
    """组装当前生产目标：只执行到链接提取或推广内容就绪。"""
    del settings, on_poll_wait
    task_repo = SqlAlchemyTaskRepository(session)
    queue_repo = SqlAlchemyQueueRepository(session)
    price_rules = SqlAlchemyPriceRuleRepository(
        session
    ).list_template_price_rules()
    preparation = TaskPreparationService(
        bundle.feishu,
        bundle.tomato,
        task_repo,
        queue_repo,
        price_rules=price_rules,
        youxuan=bundle.youxuan,
        promotion_asset_repo=SqlAlchemyPromotionAssetRepository(session),
    )
    readiness = LinkReadinessService(
        preparation,
        DeliveryFlowService(bundle.delivery, bundle.ocean),
        task_repo,
        SqlAlchemyWorkflowRepository(session),
    )

    def execute(task: DramaTask, _item: QueueItem) -> ExecutionOutcome:
        outcome = readiness.execute(
            task,
            task.target_stage,
            dry_run=not use_real_adapters,
            now=datetime.now(timezone.utc),
        )
        event = ExecutionEvent(
            task_id=task.id,
            event_type=outcome.status,
            message=_link_readiness_message(outcome.status),
            level=(
                EventLevel.ERROR
                if outcome.status == STATUS_MANUAL_REVIEW
                else EventLevel.INFO
            ),
            context_json={
                "step_name": task.current_stage,
                "target_stage": task.target_stage,
                **outcome.details,
            },
        )
        if outcome.status == STATUS_MANUAL_REVIEW:
            return ExecutionOutcome(
                status=STATUS_MANUAL_REVIEW,
                failure_code=outcome.failure_code,
                retry_safe=_is_retry_safe(outcome.failure_code),
                events=[event],
            )
        if outcome.status not in {STATUS_LINK_EXTRACTED, STATUS_LINK_READY}:
            return ExecutionOutcome(
                status=STATUS_MANUAL_REVIEW,
                failure_code=outcome.status,
                retry_safe=False,
                events=[event],
            )
        return ExecutionOutcome(status=outcome.status, events=[event])

    return execute


def _link_readiness_message(status: str) -> str:
    return {
        STATUS_LINK_EXTRACTED: "番茄链接已提取并冻结",
        STATUS_LINK_READY: "投放系统剧目与推广内容已搭建",
        STATUS_MANUAL_REVIEW: "链接准备失败，已转人工处理",
    }.get(status, f"链接准备结果: {status}")


_RETRY_SAFE_CODES = frozenset({
    "RESULT_UNCERTAIN",
    "TimeoutError",
    "SERVER_ERROR",
    "TOMATO_VIEW_BUTTON_NOT_FOUND",
    "TOMATO_LINK_VIEW_EMPTY",
    "TOMATO_LINK_AMBIGUOUS",
})

_SESSION_EXPIRED_CODES = frozenset({
    "SESSION_EXPIRED",
    "TOMATO_SESSION_EXPIRED",
    "TOMATO_LOGIN_REQUIRED",
})


def _is_retry_safe(failure_code: str | None) -> bool:
    """超时和临时性错误允许重试；会话失效不允许重试（需先重新登录）。"""
    if not failure_code:
        return False
    if failure_code in _SESSION_EXPIRED_CODES:
        return False
    return failure_code in _RETRY_SAFE_CODES


def build_worker_executor(
    settings: Settings,
    bundle: AdapterBundle,
    session: Session,
    *,
    include_test: bool = False,
    account_rows: list[AccountRow] | None = None,
    use_real_adapters: bool = False,
    poll_interval_seconds: int | None = None,
    on_poll_wait=None,
    delivery_config=None,
) -> Callable[[DramaTask, QueueItem], ExecutionOutcome]:
    """组装 Worker 真实编排执行器；account_rows 仅用于测试注入。"""
    price_rules = SqlAlchemyPriceRuleRepository(session).list_template_price_rules()
    material_ranges = SqlAlchemyMaterialRuleRepository(
        session
    ).list_material_rule_ranges()
    plan_builder = PlanSpecBuilder(
        AccountRoutingRule(),
        PromotionContentMappingRule(),
        MaterialGroupRule(),
        TaskNameRule(),
    )
    scratch_ledger_repo = _ScratchLedgerRepository()
    task_repo = SqlAlchemyTaskRepository(session)
    account_usage_repo = SqlAlchemyAccountUsageRepository(session)
    real_config = delivery_config
    if use_real_adapters and real_config is None:
        real_config = DeliveryConfigSnapshotService(
            settings.data_dir / "extracted"
        )
    preparation = TaskPreparationService(
        bundle.feishu,
        bundle.tomato,
        task_repo,
        SqlAlchemyQueueRepository(session),
        price_rules=price_rules,
        youxuan=bundle.youxuan,
        promotion_asset_repo=SqlAlchemyPromotionAssetRepository(session),
    )
    # 安全默认 False；Mock 验收测试需显式传 True 模拟完整提交链路（与 CLI Mock 模式一致）。
    delivery = StandardDeliveryService(
        PlanValidationService(),
        bundle.delivery,
        bundle.ocean,
        submit_guard,
        bundle.feishu,
        scratch_ledger_repo,
        task_repo,
        allow_final_submit=settings.allow_final_submit,
        use_real_adapters=use_real_adapters,
        poll_interval_seconds=(
            settings.poll_interval_seconds
            if poll_interval_seconds is None
            else poll_interval_seconds
        ),
        poll_timeout_seconds=settings.poll_timeout_seconds,
        on_poll_wait=on_poll_wait,
    )

    def execute(task: DramaTask, item: QueueItem) -> ExecutionOutcome:
        if task.link_status != "VALIDATED" or not task.link_set:
            preparation_outcome = preparation.prepare_task(
                task,
                dry_run=not use_real_adapters,
            )
            if preparation_outcome.status != PREPARATION_READY:
                return _link_preparation_failure(task, preparation_outcome)
            task = task_repo.get(task.id) or task

        links, link_events = _frozen_links(task)
        if links is None:
            return _outcome(STATUS_MANUAL_REVIEW, link_events)

        mapping_rows: list[dict] = []
        resources = {"material_ids": [], "title_packages": []}
        if use_real_adapters:
            try:
                mapping_rows = real_config.mapping_proposal()
                resources = real_config.task_resources(task.drama_name)
                _validate_task_resources(resources)
            except Exception as exc:
                return _outcome(
                    STATUS_MANUAL_REVIEW,
                    [*link_events, _delivery_config_error(task, exc)],
                )

        if account_rows is not None:
            allocated = _allocate_accounts(
                task.drama_name, links, include_test, account_rows
            )
            assignment_status = "ACCOUNT_BLOCK_UNAVAILABLE"
            assignment_reason = "测试注入账户块中无可用账户"
        else:
            assignment = AccountAssignmentService(
                bundle.feishu,
                usage_repo=account_usage_repo,
            ).assign(
                task.drama_name,
                links,
                allocated_cids=set(),
                dry_run=not use_real_adapters,
                include_test=include_test,
                task_id=task.id,
                usage_day=as_utc(task.available_time).astimezone(
                    SHANGHAI_TZ
                ).date(),
                candidate_validator=(
                    (lambda candidate: _real_cid_configs(candidate, mapping_rows))
                    if use_real_adapters
                    else None
                ),
            )
            allocated = (
                (
                    assignment.accounts,
                    (
                        _real_cid_configs(assignment.accounts, mapping_rows)
                        if use_real_adapters
                        else _cid_configs(assignment.accounts)
                    ),
                )
                if assignment.status
                in {AssignmentStatus.CONFIRMED, AssignmentStatus.DRY_RUN}
                else None
            )
            assignment_status = assignment.status
            assignment_reason = assignment.reason
        if allocated is None:
            return _account_assignment_failure(
                task,
                links,
                assignment_status,
                assignment_reason,
                link_events,
            )
        accounts, cid_configs = allocated

        material_ids = list(resources.get("material_ids") or [])
        title_packages = list(resources.get("title_packages") or [])
        spec = plan_builder.build(
            task,
            links,
            accounts,
            None,
            len(material_ids) if use_real_adapters else DEFAULT_MATERIAL_COUNT,
            material_ranges,
            WORKER_RULE_VERSION,
            include_test=include_test,
            material_ids=material_ids,
            title_packages=title_packages,
        )
        delivery_outcome = delivery.execute(
            spec,
            cid_configs,
            task.id,
            item.claimed_by or "worker-unknown",
        )
        if delivery_outcome.status == DELIVERY_DRY_RUN:
            return ExecutionOutcome(
                status=STATUS_DRY_RUN,
                events=[
                    *link_events,
                    _account_event(task, accounts),
                    _delivery_event(task, delivery_outcome),
                ],
            )
        if delivery_outcome.status != DELIVERY_COMPLETED:
            return ExecutionOutcome(
                status=STATUS_MANUAL_REVIEW,
                failure_code=delivery_outcome.failure_code,
                retry_safe=delivery_outcome.retry_safe,
                events=[
                    *link_events,
                    _account_event(task, accounts),
                    _delivery_error(task, delivery_outcome),
                ],
            )

        ledger = (
            scratch_ledger_repo.get(delivery_outcome.ledger_id)
            if delivery_outcome.ledger_id is not None
            else None
        )
        return ExecutionOutcome(
            status=STATUS_COMPLETED,
            external_task_id=delivery_outcome.external_task_id,
            ledger_fields=_ledger_fields(spec, ledger),
            events=[
                *link_events,
                _account_event(task, accounts),
                _delivery_event(task, delivery_outcome),
            ],
        )

    return execute


def _frozen_links(
    task: DramaTask,
) -> tuple[dict[str, str] | None, list[ExecutionEvent]]:
    """只消费已验证的冻结链接，执行阶段不再访问来源平台。"""
    links = {
        key: value
        for key, value in task.link_set.items()
        if key in {"IAA", "9.9", "2.9"} and value
    }
    if task.link_status != "VALIDATED" or not links:
        return None, [
            ExecutionEvent(
                task_id=task.id,
                event_type="LINK_EXTRACTION",
                message="任务缺少已验证的冻结链接快照",
                level=EventLevel.ERROR,
                context_json={
                    "platform": task.platform,
                    "link_status": task.link_status,
                },
            )
        ]
    return links, [
        ExecutionEvent(
            task_id=task.id,
            event_type="LINK_EXTRACTION",
            message=f"消费冻结链接快照: {list(links)}",
            level=EventLevel.INFO,
            context_json={"links": links},
        )
    ]


def _link_preparation_error(
    task: DramaTask,
    preparation_outcome: PreparationOutcome,
) -> ExecutionEvent:
    context = {
        "platform": task.platform,
        **preparation_outcome.details,
    }
    return ExecutionEvent(
        task_id=task.id,
        event_type="LINK_EXTRACTION",
        message=(
            "到点链接准备未完成: "
            f"{preparation_outcome.failure_code or preparation_outcome.status}"
        ),
        level=EventLevel.ERROR,
        context_json=context,
    )


def _link_preparation_failure(
    task: DramaTask,
    preparation_outcome: PreparationOutcome,
) -> ExecutionOutcome:
    """保留同名剧匹配失败码和证据，禁止自动重试。"""
    return ExecutionOutcome(
        status=STATUS_MANUAL_REVIEW,
        failure_code=preparation_outcome.failure_code,
        retry_safe=False,
        events=[_link_preparation_error(task, preparation_outcome)],
    )


def _allocate_accounts(
    drama_name: str,
    links: dict[str, str],
    include_test: bool,
    rows: list[AccountRow],
) -> tuple[list[dict], list[dict]] | None:
    """按链接类型分配账户块，返回 accounts dict 与 CID 配置；缺块返回 None。"""
    service = AccountAllocationService(drama_name)
    allocated: set[str] = set()
    accounts: list[dict] = []
    test_row: AccountRow | None = None

    if "IAA" in links:
        iaa = service.find_iaa_block(rows, allocated)
        if iaa is None:
            return None
        allocated.update(iaa.cids)
        accounts.extend(_account_dicts(iaa.rows))
        test_row = iaa.test_account_row

    required_iap = {link_type for link_type in ("9.9", "2.9") if link_type in links}
    if required_iap:
        iap = service.find_iap_block(rows, allocated, required_iap)
        if iap is None:
            return None
        allocated.update(iap.cids)
        accounts.extend(_account_dicts(iap.rows))

    if include_test and test_row is not None:
        accounts = _mark_test_account(accounts, test_row)
    return accounts, _cid_configs(accounts)


def _account_dicts(rows: list[AccountRow]) -> list[dict]:
    return [
        {"role": row.group, "cid": row.cid, "is_test": row.is_test}
        for row in rows
    ]


def _mark_test_account(
    accounts: list[dict],
    test_row: AccountRow,
) -> list[dict]:
    """把块内测试户行标记 is_test，避免重复追加同一 CID。"""
    return [
        {
            **account,
            "is_test": (
                True
                if account["cid"] == test_row.cid and account["role"] == "B4"
                else account["is_test"]
            ),
        }
        for account in accounts
    ]


def _cid_configs(accounts: list[dict]) -> list[dict]:
    """按 CLI _cid_configs 格式生成 CID 配置；同一 CID 只保留一份。"""
    now = datetime.now(timezone.utc)
    effective_from = (now - timedelta(days=1)).isoformat()
    seen: set[str] = set()
    configs: list[dict] = []
    for account in accounts:
        cid = str(account["cid"])
        if cid in seen:
            continue
        seen.add(cid)
        role = str(account["role"])
        configs.append(
            {
                "cid": cid,
                "subject": SUBJECT,
                "delivery_type": ROLE_DELIVERY_TYPES.get(role, role),
                "enabled": True,
                "effective_from": effective_from,
                "effective_to": None,
                "douyin_account": f"dy-{cid}",
                "ad_preset": f"ad-{cid}",
                "account_open_preset": f"open-{cid}",
            }
        )
    return configs


def _real_cid_configs(
    accounts: list[dict],
    mapping_rows: list[dict],
) -> list[dict]:
    """仅从真实采集/人工确认映射构造 CID 配置，禁止生成占位值。"""
    now = datetime.now(timezone.utc)
    by_cid: dict[str, list[dict]] = {}
    for row in mapping_rows:
        by_cid.setdefault(str(row.get("cid", "")).strip(), []).append(row)
    configs: list[dict] = []
    seen: set[str] = set()
    for account in accounts:
        cid = str(account.get("cid", "")).strip()
        if cid in seen:
            continue
        seen.add(cid)
        matches = by_cid.get(cid, [])
        if len(matches) != 1:
            raise ValidationError(
                f"CID {cid} 缺少唯一真实投放配置（匹配 {len(matches)} 条）"
            )
        row = matches[0]
        values = {
            "subject": str(row.get("company") or row.get("subject") or "").strip(),
            "douyin_account": str(row.get("douyin_account") or "").strip(),
            "ad_preset": str(row.get("ad_preset") or "").strip(),
            "account_open_preset": str(
                row.get("open_preset") or row.get("account_open_preset") or ""
            ).strip(),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValidationError(
                f"CID {cid} 真实配置不完整: {', '.join(missing)}"
            )
        role = str(account.get("role", ""))
        configs.append(
            {
                "cid": cid,
                **values,
                "delivery_type": ROLE_DELIVERY_TYPES.get(role, role),
                "enabled": True,
                "effective_from": (now - timedelta(days=1)).isoformat(),
                "effective_to": None,
            }
        )
    return configs


def _validate_task_resources(resources: dict) -> None:
    materials = list(resources.get("material_ids") or [])
    titles = list(resources.get("title_packages") or [])
    if not materials:
        raise ValidationError("剧目未配置真实素材")
    if len(titles) != 6 or len(set(titles)) != 6:
        raise ValidationError("剧目必须配置 6 个不重复标题包")


def _delivery_config_error(task: DramaTask, exc: Exception) -> ExecutionEvent:
    return ExecutionEvent(
        task_id=task.id,
        event_type="DELIVERY_CONFIG",
        message=f"真实投放配置不完整: {exc}",
        level=EventLevel.ERROR,
        context_json={"drama_name": task.drama_name},
    )


def _ledger_fields(spec: PlanSpec, ledger) -> dict:
    """从 StandardDeliveryService 内存台账提取最终台账字段。"""
    return {
        "album_id": getattr(ledger, "album_id", "") or "",
        "product_id": getattr(ledger, "product_id", "") or "",
        "task_name": getattr(ledger, "task_name", "") or spec.task_name,
        "rule_version": (
            getattr(ledger, "rule_version", "") or spec.rule_version or ""
        ),
        "config_version": getattr(ledger, "config_version", "") or CONFIG_VERSION,
    }


def _account_event(task: DramaTask, accounts: list[dict]) -> ExecutionEvent:
    return ExecutionEvent(
        task_id=task.id,
        event_type="ACCOUNT_ALLOCATION",
        message=f"账户块分配完成: {len(accounts)} 个账户",
        level=EventLevel.INFO,
        context_json={"cids": [account["cid"] for account in accounts]},
    )


def _account_assignment_failure(
    task: DramaTask,
    links: dict[str, str],
    status: str,
    reason: str,
    prior_events: list[ExecutionEvent],
) -> ExecutionOutcome:
    """保留账户写入失败语义，禁止队列把部分写误判为可安全重试。"""
    return ExecutionOutcome(
        status=STATUS_MANUAL_REVIEW,
        failure_code=status,
        retry_safe=False,
        events=[*prior_events, _account_error(task, links, status, reason)],
    )


def _account_error(
    task: DramaTask,
    links: dict[str, str],
    status: str,
    reason: str,
) -> ExecutionEvent:
    return ExecutionEvent(
        task_id=task.id,
        event_type="ACCOUNT_ALLOCATION",
        message=f"账户分配失败（{status}）：{reason}，任务转人工处理",
        level=EventLevel.ERROR,
        context_json={"links": links, "failure_code": status},
    )


def _delivery_event(task: DramaTask, outcome) -> ExecutionEvent:
    dry_run = getattr(outcome, "status", "") == DELIVERY_DRY_RUN
    return ExecutionEvent(
        task_id=task.id,
        event_type="DELIVERY",
        message=(
            f"标准投放未提交（安全开关拦截），本地流程完成: {outcome.external_task_id or '-'}"
            if dry_run
            else f"标准投放完成: {outcome.external_task_id}"
        ),
        level=EventLevel.WARNING if dry_run else EventLevel.INFO,
        context_json={"status": outcome.status, "ledger_id": outcome.ledger_id},
    )


def _delivery_error(task: DramaTask, outcome) -> ExecutionEvent:
    return ExecutionEvent(
        task_id=task.id,
        event_type="DELIVERY",
        message=(
            f"标准投放未完成: {outcome.status} "
            f"({outcome.external_task_id or '-'})"
        ),
        level=EventLevel.ERROR,
        context_json={
            "status": outcome.status,
            "external_task_id": outcome.external_task_id,
            "failure_code": outcome.failure_code,
            "retry_safe": outcome.retry_safe,
        },
    )


def _unsupported_platform(task: DramaTask) -> ExecutionOutcome:
    message = (
        "JUBIAN 暂未接入 Worker 编排，后续使用表内 J/K/L 链接"
        if task.platform == "JUBIAN"
        else f"不支持的平台: {task.platform}"
    )
    return ExecutionOutcome(
        status=STATUS_MANUAL_REVIEW,
        events=[
            ExecutionEvent(
                task_id=task.id,
                event_type="LINK_EXTRACTION",
                message=message,
                level=EventLevel.ERROR,
                context_json={"platform": task.platform},
            )
        ],
    )


def _outcome(status: str, events: list[ExecutionEvent]) -> ExecutionOutcome:
    return ExecutionOutcome(status=status, events=events)

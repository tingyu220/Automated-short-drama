"""Worker 真实编排执行器：链接提取 → 账户分配 → 标准投放。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from backend.application.services import submit_guard
from backend.application.services.account_allocation_service import (
    AccountAllocationService,
)
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
    StandardDeliveryService,
)
from backend.application.services.tomato_extraction_service import extract_iaa, scan_iap
from backend.application.services.worker_execution import (
    ExecutionOutcome,
    STATUS_COMPLETED,
    STATUS_MANUAL_REVIEW,
)
from backend.domain.execution.execution_event import EventLevel, ExecutionEvent
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.queue.queue_item import QueueItem
from backend.domain.rules.account_block import AccountRow
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
)
from backend.infrastructure.database.repositories.task_repository import (
    SqlAlchemyTaskRepository,
)
from backend.platforms.mock.mock_account_table import MOCK_ACCOUNT_ROWS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.bootstrap.adapters import AdapterBundle
    from backend.infrastructure.config.settings import Settings

DEFAULT_EPISODE_COUNT = 1
DEFAULT_MATERIAL_COUNT = 3
WORKER_RULE_VERSION = "worker-mock-v1"
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
        self._ledgers: dict[str, object] = {}

    def add(self, ledger):
        self._ledgers[ledger.id] = ledger
        return ledger

    def get(self, ledger_id: str):
        return self._ledgers.get(ledger_id)

    def update(self, ledger):
        self._ledgers[ledger.id] = ledger
        return ledger

    def list_by_task(self, task_id: str):
        return [l for l in self._ledgers.values() if l.task_id == task_id]

    def list_all(self):
        return list(self._ledgers.values())


def build_worker_executor(
    settings: Settings,
    bundle: AdapterBundle,
    session: Session,
    *,
    include_test: bool = False,
    account_rows: list[AccountRow] | None = None,
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
    rows = MOCK_ACCOUNT_ROWS if account_rows is None else account_rows
    scratch_ledger_repo = _ScratchLedgerRepository()
    delivery = StandardDeliveryService(
        PlanValidationService(),
        bundle.delivery,
        bundle.ocean,
        submit_guard,
        bundle.feishu,
        scratch_ledger_repo,
        SqlAlchemyTaskRepository(session),
        allow_final_submit=settings.allow_final_submit,
        # Mock 模式同样模拟完整提交链路（与 CLI Mock 模式一致），真实提交由开关把关。
        use_real_adapters=True,
    )

    def execute(task: DramaTask, item: QueueItem) -> ExecutionOutcome:
        if task.platform != "TOMATO":
            return _unsupported_platform(task)

        links, link_events = _extract_links(task, bundle.tomato, price_rules)
        if links is None:
            return _outcome(STATUS_MANUAL_REVIEW, link_events)

        allocated = _allocate_accounts(
            task.drama_name, links, include_test, rows
        )
        if allocated is None:
            return _outcome(
                STATUS_MANUAL_REVIEW,
                [*link_events, _account_error(task, links)],
            )
        accounts, cid_configs = allocated

        spec = plan_builder.build(
            task,
            links,
            accounts,
            None,
            DEFAULT_MATERIAL_COUNT,
            material_ranges,
            WORKER_RULE_VERSION,
            include_test=include_test,
        )
        delivery_outcome = delivery.execute(
            spec,
            cid_configs,
            task.id,
            item.claimed_by or "worker-unknown",
        )
        if delivery_outcome.status != DELIVERY_COMPLETED:
            return _outcome(
                STATUS_MANUAL_REVIEW,
                [
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


def _extract_links(
    task: DramaTask,
    tomato,
    price_rules: list,
) -> tuple[dict[str, str] | None, list[ExecutionEvent]]:
    """番茄 IAA + IAP 链接提取；异常或空链接返回失败事件。"""
    try:
        iaa = extract_iaa(task.drama_name, DEFAULT_EPISODE_COUNT, tomato)
        scan = scan_iap(task.drama_name, tomato, price_rules)
        links = {"IAA": iaa.promotion_url}
        if scan.iap_2_9_link is not None:
            links["2.9"] = scan.iap_2_9_link.promotion_url
        if scan.iap_9_9_link is not None:
            links["9.9"] = scan.iap_9_9_link.promotion_url
    except Exception as exc:
        return None, [
            ExecutionEvent(
                task_id=task.id,
                event_type="LINK_EXTRACTION",
                message=f"番茄链接提取失败: {exc}",
                level=EventLevel.ERROR,
                context_json={"platform": task.platform},
            )
        ]
    if not links:
        return None, [
            ExecutionEvent(
                task_id=task.id,
                event_type="LINK_EXTRACTION",
                message="未获取到任何可用推广链接",
                level=EventLevel.ERROR,
                context_json={"platform": task.platform},
            )
        ]
    return links, [
        ExecutionEvent(
            task_id=task.id,
            event_type="LINK_EXTRACTION",
            message=f"番茄链接提取完成: {list(links)}",
            level=EventLevel.INFO,
            context_json={"links": links},
        )
    ]


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


def _account_error(task: DramaTask, links: dict[str, str]) -> ExecutionEvent:
    return ExecutionEvent(
        task_id=task.id,
        event_type="ACCOUNT_ALLOCATION",
        message="无可用 IAA/IAP 账户块，任务转人工处理",
        level=EventLevel.ERROR,
        context_json={"links": links},
    )


def _delivery_event(task: DramaTask, outcome) -> ExecutionEvent:
    return ExecutionEvent(
        task_id=task.id,
        event_type="DELIVERY",
        message=f"标准投放完成: {outcome.external_task_id}",
        level=EventLevel.INFO,
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

"""飞书账户条件整块分配编排。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from collections.abc import Callable

from backend.application.services.account_allocation_service import (
    AccountAllocationService,
    BlockAllocation,
)
from backend.domain.rules.account_block import AccountRow
from backend.domain.rules.account_block import BLOCK_DEFINITIONS, BlockDefinition
from backend.domain.rules.account_sheet import AccountUsage


class AssignmentStatus:
    CONFIRMED = "CONFIRMED"
    CONFLICT = "CONFLICT"
    PARTIAL_WRITE = "PARTIAL_WRITE"
    DRY_RUN = "DRY_RUN"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AccountAssignmentResult:
    status: str
    accounts: list[dict] = field(default_factory=list)
    reason: str = ""


class AccountAssignmentService:
    def __init__(self, feishu, *, usage_repo=None) -> None:
        self._feishu = feishu
        self._usage_repo = usage_repo

    def assign(
        self,
        drama_name: str,
        links: dict[str, str],
        *,
        allocated_cids: set[str],
        dry_run: bool,
        include_test: bool = False,
        task_id: str | None = None,
        usage_day: date | None = None,
        candidate_validator: Callable[[list[dict]], None] | None = None,
    ) -> AccountAssignmentResult:
        allocator = AccountAllocationService(drama_name)
        planned: list[tuple[str, BlockAllocation]] = []
        used_today = set(allocated_cids)
        if self._usage_repo is not None and usage_day is not None:
            used_today.update(self._usage_repo.used_cids(usage_day))
        reserved = set(used_today)

        if links.get("IAA"):
            iaa_rows = self._feishu.read_account_rows("IAA")
            reserved.update(row.cid for row in iaa_rows if row.drama_name)
            allocation = allocator.find_iaa_block(
                iaa_rows, reserved
            )
            if allocation is None:
                try:
                    allocation = self._append_and_allocate(
                        "IAA",
                        iaa_rows,
                        allocator,
                        used_today,
                        dry_run=dry_run,
                        candidate_validator=candidate_validator,
                        include_test=include_test,
                    )
                except Exception as exc:
                    return AccountAssignmentResult(
                        AssignmentStatus.CONFLICT,
                        reason=str(exc),
                    )
            if allocation is None:
                return AccountAssignmentResult(
                    AssignmentStatus.UNAVAILABLE,
                    reason="没有完整可用的 IAA 账户块",
                )
            planned.append(("IAA", allocation))
            used_today.update(allocation.cids)
            reserved.update(allocation.cids)

        paid_types = {key for key in ("9.9", "2.9") if links.get(key)}
        if paid_types:
            iap_rows = self._feishu.read_account_rows("IAP")
            reserved.update(row.cid for row in iap_rows if row.drama_name)
            allocation = allocator.find_iap_block(
                iap_rows, reserved, paid_types
            )
            if allocation is None:
                try:
                    allocation = self._append_and_allocate(
                        "IAP",
                        iap_rows,
                        allocator,
                        used_today,
                        required=paid_types,
                        dry_run=dry_run,
                        candidate_validator=candidate_validator,
                        include_test=include_test,
                    )
                except Exception as exc:
                    return AccountAssignmentResult(
                        AssignmentStatus.CONFLICT,
                        reason=str(exc),
                    )
            if allocation is None:
                return AccountAssignmentResult(
                    AssignmentStatus.UNAVAILABLE,
                    reason="没有满足价格组合的完整 IAP 账户块",
                )
            planned.append(("IAP", allocation))

        if not planned:
            return AccountAssignmentResult(
                AssignmentStatus.UNAVAILABLE,
                reason="任务没有需要分配账户的有效链接",
            )

        accounts = _accounts(planned, include_test)
        if candidate_validator is not None:
            try:
                candidate_validator(accounts)
            except Exception as exc:
                return AccountAssignmentResult(
                    AssignmentStatus.CONFLICT,
                    accounts,
                    str(exc),
                )
        if dry_run:
            return AccountAssignmentResult(AssignmentStatus.DRY_RUN, accounts)

        for kind, allocation in planned:
            latest = self._feishu.read_account_rows(kind)
            if not _still_available(allocation.rows, latest):
                return AccountAssignmentResult(
                    AssignmentStatus.CONFLICT,
                    accounts,
                    "写入前回读发现账户块已变化",
                )

        written = False
        try:
            for kind, allocation in planned:
                assignments = {
                    row.row_number: drama_name for row in allocation.rows
                }
                self._feishu.write_account_names(kind, assignments)
                written = True
                test_row_number = None
                if include_test and allocation.test_account_row is not None:
                    test_row_number = allocation.test_account_row.row_number
                    self._feishu.write_account_test_flags(
                        kind, {test_row_number}
                    )
                read_back = self._feishu.read_account_rows(kind)
                if not _write_confirmed(
                    allocation.rows,
                    read_back,
                    drama_name,
                    test_row_number=test_row_number,
                ):
                    return AccountAssignmentResult(
                        AssignmentStatus.PARTIAL_WRITE,
                        accounts,
                        f"{kind} 账户块写入后回读不一致",
                    )
            if (
                self._usage_repo is not None
                and task_id is not None
                and usage_day is not None
            ):
                self._usage_repo.record_confirmed(
                    [
                        AccountUsage(
                            task_id=task_id,
                            drama_name=drama_name,
                            usage_day=usage_day,
                            cid=str(account["cid"]),
                            role=str(account["role"]),
                            sheet_kind=str(account["sheet_kind"]),
                            row_number=int(account["row_number"]),
                        )
                        for account in accounts
                    ]
                )
        except Exception as exc:
            status = (
                AssignmentStatus.PARTIAL_WRITE
                if written
                else AssignmentStatus.CONFLICT
            )
            return AccountAssignmentResult(status, accounts, str(exc))
        return AccountAssignmentResult(AssignmentStatus.CONFIRMED, accounts)

    def _append_and_allocate(
        self,
        kind: str,
        rows: list[AccountRow],
        allocator: AccountAllocationService,
        used_today: set[str],
        *,
        required: set[str] | None = None,
        dry_run: bool,
        candidate_validator: Callable[[list[dict]], None] | None,
        include_test: bool,
    ) -> BlockAllocation | None:
        """从最近完整启用块复制空白标准块，再按本次价格组合分配。"""
        template = _latest_append_template(
            rows,
            BLOCK_DEFINITIONS[kind],
            used_today,
        )
        if template is None:
            return None
        last_row = max((row.row_number for row in rows), default=1)
        preview_rows = _preview_appended_rows(last_row, template)
        preview = (
            allocator.find_iaa_block(preview_rows, used_today)
            if kind == "IAA"
            else allocator.find_iap_block(
                preview_rows,
                used_today,
                required or set(),
            )
        )
        if preview is None:
            return None
        if candidate_validator is not None:
            candidate_validator(_accounts([(kind, preview)], include_test))
        if dry_run:
            return preview
        appended = self._feishu.append_account_block(
            kind,
            last_row,
            template,
        )
        if kind == "IAA":
            return allocator.find_iaa_block(appended, used_today)
        return allocator.find_iap_block(appended, used_today, required or set())


def _accounts(
    planned: list[tuple[str, BlockAllocation]], include_test: bool
) -> list[dict]:
    return [
        {
            "role": row.group,
            "cid": row.cid,
            "is_test": row.is_test or (
                include_test
                and allocation.test_account_row is not None
                and row.row_number == allocation.test_account_row.row_number
            ),
            "row_number": row.row_number,
            "sheet_kind": kind,
        }
        for kind, allocation in planned
        for row in allocation.rows
    ]


def _still_available(expected: list[AccountRow], latest: list[AccountRow]) -> bool:
    by_row = {row.row_number: row for row in latest}
    for original in expected:
        current = by_row.get(original.row_number)
        if (
            current is None
            or current.cid != original.cid
            or current.group != original.group
            or not current.enabled
            or bool(current.drama_name)
        ):
            return False
    return True


def _write_confirmed(
    expected: list[AccountRow],
    latest: list[AccountRow],
    drama_name: str,
    *,
    test_row_number: int | None,
) -> bool:
    by_row = {row.row_number: row for row in latest}
    return all(
        (current := by_row.get(original.row_number)) is not None
        and current.cid == original.cid
        and current.drama_name == drama_name
        and (test_row_number != original.row_number or current.is_test)
        for original in expected
    )


def _latest_append_template(
    rows: list[AccountRow],
    definition: BlockDefinition,
    used_today: set[str],
) -> list[AccountRow] | None:
    size = sum(count for _, count in definition.group_patterns)
    expected_groups = [
        group
        for group, count in definition.group_patterns
        for _ in range(count)
    ]
    for start in range(len(rows) - size, -1, -1):
        block = rows[start : start + size]
        if [row.group for row in block] != expected_groups:
            continue
        if any(
            not row.enabled
            or not row.cid
            or not row.name
            or row.cid in used_today
            for row in block
        ):
            continue
        return block
    return None


def _preview_appended_rows(
    last_row: int,
    template: list[AccountRow],
) -> list[AccountRow]:
    return [
        AccountRow(
            row_number=last_row + offset,
            name=row.name,
            cid=row.cid,
            group=row.group,
            enabled=row.enabled,
            is_test=False,
            drama_name="",
        )
        for offset, row in enumerate(template, start=1)
    ]

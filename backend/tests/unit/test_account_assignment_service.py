"""飞书账户条件整块分配测试。"""
from __future__ import annotations

from copy import deepcopy
from datetime import date

from backend.application.services.account_assignment_service import (
    AccountAssignmentService,
    AssignmentStatus,
)
from backend.domain.rules.account_block import AccountRow


def _iaa_rows() -> list[AccountRow]:
    groups = ["B1"] * 3 + ["B4"] * 3 + ["B7"] * 3 + ["BX"]
    return [
        AccountRow(i + 2, f"账户{i}", f"cid-{i}", group, True, False, "")
        for i, group in enumerate(groups)
    ]


def _iap_rows() -> list[AccountRow]:
    groups = ["B1-9.9"] * 3 + ["B2-2.9"] * 3
    return [
        AccountRow(i + 20, f"付费账户{i}", f"iap-cid-{i}", group, True, False, "")
        for i, group in enumerate(groups)
    ]


class AccountFeishu:
    def __init__(
        self,
        rows,
        *,
        iap_rows=None,
        mutate_before_write=False,
        partial_write=False,
    ):
        self.rows = {"IAA": deepcopy(rows), "IAP": deepcopy(iap_rows or [])}
        self.read_count = 0
        self.writes: list[tuple[str, dict[int, str]]] = []
        self.test_flag_writes: list[tuple[str, set[int]]] = []
        self.mutate_before_write = mutate_before_write
        self.partial_write = partial_write
        self.append_calls: list[tuple[str, int, list[AccountRow]]] = []

    def read_account_rows(self, kind):
        self.read_count += 1
        if self.mutate_before_write and self.read_count == 2:
            self.rows[kind][0].drama_name = "其他剧"
        return deepcopy(self.rows[kind])

    def write_account_names(self, kind, assignments):
        self.writes.append((kind, dict(assignments)))
        applied = list(assignments.items())[:1] if self.partial_write else assignments.items()
        by_row = {row.row_number: row for row in self.rows[kind]}
        for row_number, drama_name in applied:
            by_row[row_number].drama_name = drama_name

    def write_account_test_flags(self, kind, row_numbers):
        self.test_flag_writes.append((kind, set(row_numbers)))
        by_row = {row.row_number: row for row in self.rows[kind]}
        for row_number in row_numbers:
            by_row[row_number].is_test = True

    def append_account_block(self, kind, expected_last_row, template_rows):
        self.append_calls.append(
            (kind, expected_last_row, deepcopy(template_rows))
        )
        appended = [
            AccountRow(
                expected_last_row + offset,
                row.name,
                row.cid,
                row.group,
                row.enabled,
                False,
                "",
            )
            for offset, row in enumerate(template_rows, start=1)
        ]
        self.rows[kind].extend(deepcopy(appended))
        return appended


class UsageRepo:
    def __init__(self, used=None):
        self.used = set(used or set())
        self.recorded = []

    def used_cids(self, usage_day):
        return set(self.used)

    def record_confirmed(self, usages):
        self.recorded.extend(usages)


def test_confirmed_iaa_assignment_writes_and_reads_back_ten_rows() -> None:
    feishu = AccountFeishu(_iaa_rows())

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids=set(),
        dry_run=False,
    )

    assert result.status == AssignmentStatus.CONFIRMED
    assert len(result.accounts) == 10
    assert len(feishu.writes) == 1
    assert list(feishu.writes[0][1]) == list(range(2, 12))


def test_write_time_conflict_never_overwrites_existing_drama() -> None:
    feishu = AccountFeishu(_iaa_rows(), mutate_before_write=True)

    result = AccountAssignmentService(feishu).assign(
        "新剧", {"IAA": "link"}, allocated_cids=set(), dry_run=False
    )

    assert result.status == AssignmentStatus.CONFLICT
    assert feishu.writes == []


def test_partial_write_is_detected_by_read_back() -> None:
    feishu = AccountFeishu(_iaa_rows(), partial_write=True)

    result = AccountAssignmentService(feishu).assign(
        "新剧", {"IAA": "link"}, allocated_cids=set(), dry_run=False
    )

    assert result.status == AssignmentStatus.PARTIAL_WRITE
    assert "回读" in result.reason


def test_dry_run_returns_preview_without_writing() -> None:
    feishu = AccountFeishu(_iaa_rows())

    result = AccountAssignmentService(feishu).assign(
        "新剧", {"IAA": "link"}, allocated_cids=set(), dry_run=True
    )

    assert result.status == AssignmentStatus.DRY_RUN
    assert len(result.accounts) == 10
    assert feishu.writes == []


def test_cid_marked_used_today_is_not_allocated_again() -> None:
    rows = _iaa_rows()
    occupied = AccountRow(
        1,
        "历史账户",
        rows[0].cid,
        "OTHER",
        True,
        False,
        "已分配剧",
    )
    feishu = AccountFeishu([occupied, *rows])

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids={rows[0].cid},
        dry_run=False,
    )

    assert result.status == AssignmentStatus.UNAVAILABLE
    assert feishu.writes == []


def test_include_test_marks_one_b4_and_confirms_read_back() -> None:
    feishu = AccountFeishu(_iaa_rows())

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids=set(),
        dry_run=False,
        include_test=True,
    )

    assert result.status == AssignmentStatus.CONFIRMED
    assert feishu.test_flag_writes == [("IAA", {5})]
    assert [account for account in result.accounts if account["is_test"]] == [
        {
            "role": "B4",
            "cid": "cid-3",
            "is_test": True,
            "row_number": 5,
            "sheet_kind": "IAA",
        }
    ]


def test_single_paid_link_assigns_only_matching_three_iap_rows() -> None:
    feishu = AccountFeishu([], iap_rows=_iap_rows())

    result = AccountAssignmentService(feishu).assign(
        "付费剧",
        {"9.9": "link"},
        allocated_cids=set(),
        dry_run=False,
    )

    assert result.status == AssignmentStatus.CONFIRMED
    assert [account["role"] for account in result.accounts] == ["B1-9.9"] * 3
    assert list(feishu.writes[0][1]) == [20, 21, 22]


def test_dual_paid_links_assign_six_iap_rows_atomically() -> None:
    feishu = AccountFeishu([], iap_rows=_iap_rows())

    result = AccountAssignmentService(feishu).assign(
        "双价剧",
        {"9.9": "link", "2.9": "link"},
        allocated_cids=set(),
        dry_run=False,
    )

    assert result.status == AssignmentStatus.CONFIRMED
    assert len(result.accounts) == 6
    assert list(feishu.writes[0][1]) == list(range(20, 26))


def test_no_empty_block_appends_latest_unused_template_then_assigns() -> None:
    occupied = _iaa_rows()
    for row in occupied:
        row.drama_name = "历史剧"
    feishu = AccountFeishu(occupied)

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids=set(),
        dry_run=False,
    )

    assert result.status == AssignmentStatus.CONFIRMED
    assert len(feishu.append_calls) == 1
    assert list(feishu.writes[0][1]) == list(range(12, 22))


def test_append_refuses_template_whose_cid_was_used_today() -> None:
    occupied = _iaa_rows()
    for row in occupied:
        row.drama_name = "历史剧"
    feishu = AccountFeishu(occupied)

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids={occupied[0].cid},
        dry_run=False,
    )

    assert result.status == AssignmentStatus.UNAVAILABLE
    assert feishu.append_calls == []


def test_confirmed_assignment_reads_and_records_persistent_daily_usage() -> None:
    usage_repo = UsageRepo()
    feishu = AccountFeishu(_iaa_rows())

    result = AccountAssignmentService(
        feishu,
        usage_repo=usage_repo,
    ).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids=set(),
        dry_run=False,
        task_id="task-1",
        usage_day=date(2026, 8, 10),
    )

    assert result.status == AssignmentStatus.CONFIRMED
    assert len(usage_repo.recorded) == 10
    assert {usage.task_id for usage in usage_repo.recorded} == {"task-1"}
    assert {usage.usage_day for usage in usage_repo.recorded} == {
        date(2026, 8, 10)
    }


def test_candidate_validation_failure_happens_before_feishu_write() -> None:
    feishu = AccountFeishu(_iaa_rows())

    def reject(_accounts):
        raise ValueError("缺少真实 CID 配置")

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids=set(),
        dry_run=False,
        candidate_validator=reject,
    )

    assert result.status == AssignmentStatus.CONFLICT
    assert "缺少真实 CID 配置" in result.reason
    assert feishu.writes == []


def test_candidate_validation_failure_happens_before_append_write() -> None:
    occupied = _iaa_rows()
    for row in occupied:
        row.drama_name = "历史剧"
    feishu = AccountFeishu(occupied)

    result = AccountAssignmentService(feishu).assign(
        "新剧",
        {"IAA": "link"},
        allocated_cids=set(),
        dry_run=False,
        candidate_validator=lambda _accounts: (_ for _ in ()).throw(
            ValueError("缺少真实 CID 配置")
        ),
    )

    assert result.status == AssignmentStatus.CONFLICT
    assert feishu.append_calls == []

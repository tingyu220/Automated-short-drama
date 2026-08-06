"""PlanSpec 校验服务单元测试：通过用例与全部失败用例."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.application.services.plan_validation_service import (
    PlanValidationService,
    ValidationIssue,
)
from backend.domain.plans.plan_spec import MaterialPlan, PlanSpec

UTC = timezone.utc
NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
_MISSING = object()


def _cid_config(
    cid: str,
    *,
    delivery_type: str = "IAA",
    enabled: bool = True,
    effective_from: datetime | None = None,
    douyin_account: str = "B1",
    ad_preset: str = "预设A",
    account_open_preset: str = "开户A",
) -> dict:
    return {
        "subject": "主体A",
        "delivery_type": delivery_type,
        "cid": cid,
        "ad_preset": ad_preset,
        "douyin_account": douyin_account,
        "account_open_preset": account_open_preset,
        "effective_from": effective_from or NOW - timedelta(days=1),
        "enabled": enabled,
    }


def _spec(
    *,
    link_set: dict[str, str] | None = None,
    account_cids: list[str] | None = None,
    task_name: str = "番茄#端付我的剧20260807ubr-20260807-181530-1",
    material_groups: MaterialPlan | object = _MISSING,
    expected_project_count: int = 3,
) -> PlanSpec:
    if link_set is None:
        link_set = {
            "IAA": "https://iaa/1",
            "9.9": "https://iap/9.9",
            "2.9": "https://iap/2.9",
        }
    if account_cids is None:
        account_cids = [
            "cid-b1",
            "cid-b4",
            "cid-b7",
            "cid-bx",
            "cid-iap-9-9",
            "cid-iap-2-9",
        ]
    return PlanSpec(
        drama_name="我的剧",
        platform="番茄",
        task_name=task_name,
        link_set=link_set,
        account_cids=account_cids,
        material_groups=(
            MaterialPlan(1, 2, 3, 1, 3)
            if material_groups is _MISSING
            else material_groups
        ),
        expected_project_count=expected_project_count,
    )


def _valid_configs() -> list[dict]:
    return [
        _cid_config("cid-b1"),
        _cid_config("cid-b4"),
        _cid_config("cid-b7"),
        _cid_config("cid-bx"),
        _cid_config("cid-iap-9-9", delivery_type="B1-9.9"),
        _cid_config("cid-iap-2-9", delivery_type="B2-2.9"),
    ]


class TestPlanValidationService:
    """校验服务通过/失败行为。"""

    def test_valid_spec_passes(self) -> None:
        service = PlanValidationService(now_provider=lambda: NOW)

        report = service.validate(_spec(), _valid_configs())

        assert report.passed is True
        assert report.issues == []

    def test_link_set_empty(self) -> None:
        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(link_set={}), _valid_configs()
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["LINK_SET_EMPTY"]
        assert report.issues[0].field == "link_set"

    def test_cid_config_missing(self) -> None:
        configs = [config for config in _valid_configs() if config["cid"] != "cid-b1"]

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["CID_CONFIG_MISSING"]
        assert "cid-b1" in report.issues[0].message

    def test_cid_config_duplicate(self) -> None:
        configs = _valid_configs() + [_cid_config("cid-b1")]

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["CID_CONFIG_MISSING"]

    def test_cid_config_disabled(self) -> None:
        configs = _valid_configs()
        configs[0] = _cid_config("cid-b1", enabled=False)

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["CID_CONFIG_MISSING"]

    def test_cid_config_effective_from_future(self) -> None:
        configs = _valid_configs()
        configs[0] = _cid_config(
            "cid-b1", effective_from=NOW + timedelta(days=1)
        )

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["CID_CONFIG_MISSING"]

    def test_cid_config_effective_to_expired(self) -> None:
        configs = _valid_configs()
        configs[0]["effective_to"] = NOW - timedelta(hours=1)

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["CID_CONFIG_MISSING"]

    def test_template_account_mismatch(self) -> None:
        configs = [
            config
            for config in _valid_configs()
            if config["cid"] != "cid-iap-9-9"
        ]

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == [
            "CID_CONFIG_MISSING",
            "TEMPLATE_ACCOUNT_MISMATCH",
        ]
        mismatch = report.issues[1]
        assert mismatch.field == "link_set.9.9"

    def test_douyin_account_empty(self) -> None:
        configs = _valid_configs()
        configs[0] = _cid_config("cid-b1", douyin_account="")

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["DOUYIN_ACCOUNT_EMPTY"]
        assert report.issues[0].field == "cid_configs.douyin_account"

    def test_preset_incomplete(self) -> None:
        configs = _valid_configs()
        configs[0] = _cid_config("cid-b1", ad_preset="")
        configs[1] = _cid_config("cid-b4", account_open_preset="")

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == [
            "PRESET_INCOMPLETE",
            "PRESET_INCOMPLETE",
        ]

    def test_material_groups_missing(self) -> None:
        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(material_groups=None), _valid_configs()
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["MATERIAL_COUNT_INVALID"]

    def test_expected_project_count_zero(self) -> None:
        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(expected_project_count=0), _valid_configs()
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["MATERIAL_COUNT_INVALID"]

    def test_task_name_empty(self) -> None:
        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(task_name=""), _valid_configs()
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["TASK_NAME_INVALID"]

    def test_task_name_without_marker(self) -> None:
        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(task_name="番茄#端付我的剧"), _valid_configs()
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["TASK_NAME_INVALID"]

    def test_accepts_iso_effective_time(self) -> None:
        configs = _valid_configs()
        configs[0]["effective_from"] = "2026-08-06T00:00:00+00:00"

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(), configs
        )

        assert report.passed is True

    def test_accumulates_all_issue_types(self) -> None:
        report = PlanValidationService(now_provider=lambda: NOW).validate(
            _spec(
                link_set={},
                account_cids=[],
                task_name="",
                material_groups=None,
                expected_project_count=0,
            ),
            [],
        )

        codes = [issue.code for issue in report.issues]
        assert codes == [
            "LINK_SET_EMPTY",
            "MATERIAL_COUNT_INVALID",
            "TASK_NAME_INVALID",
        ]
        assert report.passed is False

    def test_issue_dataclass_shape(self) -> None:
        issue = ValidationIssue(code="X", message="msg", field="f")

        assert issue.code == "X"
        assert issue.message == "msg"
        assert issue.field == "f"

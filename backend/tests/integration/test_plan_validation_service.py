"""PlanSpec 校验服务集成测试：Builder 生成 spec + 构造 cid_configs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.services.plan_rules import (
    AccountRoutingRule,
    MaterialGroupRule,
    PromotionContentMappingRule,
    TaskNameRule,
)
from backend.application.services.plan_spec_service import PlanSpecBuilder
from backend.application.services.plan_validation_service import (
    PlanValidationService,
)
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.tasks.drama_task import DramaTask

UTC = timezone.utc
NOW = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)


def _ranges() -> list[MaterialRuleRange]:
    return [
        MaterialRuleRange(
            min_material_count=0,
            max_material_count=30,
            strategy="BASE_1_COPY_2",
            base_group_count=1,
            copy_count=2,
            group_size_cap=30,
            target_project_count=3,
        ),
        MaterialRuleRange(
            min_material_count=31,
            max_material_count=60,
            strategy="BASE_2_COPY_2",
            base_group_count=2,
            copy_count=2,
            group_size_cap=30,
            target_project_count=3,
        ),
    ]


def _build_spec() -> PlanSpec:
    task = DramaTask(
        id="task-8-2",
        drama_name="我的剧",
        platform="番茄",
        available_time=datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
    )
    accounts = [
        {"role": "B1", "cid": "cid-b1"},
        {"role": "B4", "cid": "cid-b4"},
        {"role": "B7", "cid": "cid-b7"},
        {"role": "BX", "cid": "cid-bx"},
        {"role": "B1-9.9", "cid": "cid-iap-9-9"},
        {"role": "B2-2.9", "cid": "cid-iap-2-9"},
    ]
    links = {
        "IAA": "https://iaa/1",
        "9.9": "https://iap/9.9",
        "2.9": "https://iap/2.9",
    }
    builder = PlanSpecBuilder(
        AccountRoutingRule(),
        PromotionContentMappingRule(),
        MaterialGroupRule(),
        TaskNameRule(),
    )
    return builder.build(
        task,
        links,
        accounts,
        "product-1",
        20,
        _ranges(),
        "v1",
    )


def _cid_config(cid: str, delivery_type: str) -> dict:
    return {
        "subject": "主体A",
        "delivery_type": delivery_type,
        "cid": cid,
        "ad_preset": "预设A",
        "douyin_account": "B1",
        "account_open_preset": "开户A",
        "effective_from": NOW - timedelta(days=1),
        "enabled": True,
    }


def _valid_configs(spec: PlanSpec) -> list[dict]:
    delivery_types = {
        "cid-b1": "IAA",
        "cid-b4": "IAA",
        "cid-b7": "IAA",
        "cid-bx": "IAA",
        "cid-iap-9-9": "B1-9.9",
        "cid-iap-2-9": "B2-2.9",
    }
    return [
        _cid_config(cid, delivery_types[cid])
        for cid in spec.account_cids
    ]


class TestPlanValidationServiceIntegration:
    """Builder 产物与校验服务的端到端契约。"""

    def test_builder_output_validates(self) -> None:
        spec = _build_spec()

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            spec, _valid_configs(spec)
        )

        assert report.passed is True
        assert report.issues == []

    def test_builder_output_fails_on_disabled_cid_config(self) -> None:
        spec = _build_spec()
        configs = _valid_configs(spec)
        configs[0]["enabled"] = False

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            spec, configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["CID_CONFIG_MISSING"]

    def test_builder_output_fails_on_missing_douyin_account(self) -> None:
        spec = _build_spec()
        configs = _valid_configs(spec)
        configs[0]["douyin_account"] = ""

        report = PlanValidationService(now_provider=lambda: NOW).validate(
            spec, configs
        )

        assert report.passed is False
        assert [issue.code for issue in report.issues] == ["DOUYIN_ACCOUNT_EMPTY"]

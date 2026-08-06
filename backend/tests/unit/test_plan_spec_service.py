"""PlanSpec 生成服务单元测试：纯规则与 Builder 组合."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytest

from backend.application.services.plan_rules import (
    AccountRoutingRule,
    MaterialGroupRule,
    PromotionContentMappingRule,
    TaskNameRule,
)
from backend.application.services.plan_spec_service import PlanSpecBuilder
from backend.domain.plans.plan_spec import MaterialPlan
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.tasks.drama_task import DramaTask

UTC = timezone.utc


def _range(
    min_count: int,
    max_count: int | None,
    strategy: str,
    base: int,
    copy: int,
    *,
    cap: int = 30,
    target: int = 3,
) -> MaterialRuleRange:
    return MaterialRuleRange(
        min_material_count=min_count,
        max_material_count=max_count,
        strategy=strategy,
        base_group_count=base,
        copy_count=copy,
        group_size_cap=cap,
        target_project_count=target,
    )


NORMAL_RANGES = [
    _range(0, 30, "BASE_1_COPY_2", 1, 2),
    _range(31, 60, "BASE_2_COPY_2", 2, 2),
    _range(61, 90, "BASE_3_COPY_1", 3, 1),
]

TEST_RANGES = [
    _range(0, 19, "TEST_GROUP_2", 2, 0),
    _range(20, None, "TEST_GROUP_3", 3, 0),
]


class TestAccountRoutingRule:
    """账户路由规则测试。"""

    def test_routes_iaa_and_iap_roles(self) -> None:
        accounts = [
            {"role": "B1", "cid": "cid-b1"},
            {"role": "B4", "cid": "cid-b4"},
            {"role": "B7", "cid": "cid-b7"},
            {"role": "BX", "cid": "cid-bx"},
            {"role": "B1-9.9", "cid": "cid-b1-9-9"},
            {"role": "B2-2.9", "cid": "cid-b2-2-9"},
        ]

        result = AccountRoutingRule().build(
            {"IAA", "9.9", "2.9"}, accounts, include_test=False
        )

        assert result == {
            "IAA": ["cid-b1", "cid-b4", "cid-b7", "cid-bx"],
            "9.9": ["cid-b1-9-9"],
            "2.9": ["cid-b2-2-9"],
        }

    def test_only_returns_requested_link_types(self) -> None:
        accounts = [
            {"role": "B1-9.9", "cid": "cid-b1-9-9"},
            {"role": "B2-2.9", "cid": "cid-b2-2-9"},
        ]

        result = AccountRoutingRule().build({"9.9"}, accounts, include_test=False)

        assert list(result) == ["9.9"]

    def test_iap_role_normalization(self) -> None:
        accounts = [
            {"role": "B1-9.9", "cid": "cid-iap-b1"},
            {"role": "B2-2.9", "cid": "cid-iap-b2"},
        ]

        result = AccountRoutingRule().build(
            {"9.9", "2.9"}, accounts, include_test=False
        )

        assert result == {
            "9.9": ["cid-iap-b1"],
            "2.9": ["cid-iap-b2"],
        }

    def test_include_test_appends_test_b4(self) -> None:
        accounts = [
            {"role": "B1", "cid": "cid-b1"},
            {"role": "B4", "cid": "cid-b4"},
            {"role": "B4", "cid": "cid-test", "is_test": True},
        ]

        result = AccountRoutingRule().build(
            {"IAA"}, accounts, include_test=True
        )

        assert result["IAA"] == ["cid-b1", "cid-b4", "cid-test"]

    def test_include_test_dedupes_existing_b4(self) -> None:
        accounts = [
            {"role": "B4", "cid": "cid-b4", "is_test": True},
        ]

        result = AccountRoutingRule().build(
            {"IAA"}, accounts, include_test=True
        )

        assert result["IAA"] == ["cid-b4"]


class TestPromotionContentMappingRule:
    """推广内容映射规则测试。"""

    def test_builds_mapping_for_existing_link_types(self) -> None:
        result = PromotionContentMappingRule().build(
            "番茄", "我的剧", {"IAA", "9.9", "2.9"}
        )

        assert result == {
            "IAA": "iaa-番茄-我的剧",
            "9.9": "9.9-番茄-我的剧",
            "2.9": "2.9-番茄-我的剧",
        }

    def test_builds_mapping_for_partial_link_types(self) -> None:
        result = PromotionContentMappingRule().build(
            "剧变", "短剧B", {"2.9"}
        )

        assert result == {"2.9": "2.9-剧变-短剧B"}


class TestMaterialGroupRule:
    """素材分组规则测试。"""

    def test_normal_n_leq_30(self) -> None:
        plan = MaterialGroupRule().calculate(30, NORMAL_RANGES)

        assert plan == MaterialPlan(1, 2, 3, 1, 3)

    def test_normal_n_31_to_60(self) -> None:
        plan = MaterialGroupRule().calculate(31, NORMAL_RANGES)

        assert plan == MaterialPlan(2, 2, 6, 2, 3)

    def test_normal_n_61_to_90(self) -> None:
        plan = MaterialGroupRule().calculate(90, NORMAL_RANGES)

        assert plan == MaterialPlan(3, 1, 6, 2, 3)

    def test_normal_n_over_90_even_split(self) -> None:
        plan = MaterialGroupRule().calculate(120, NORMAL_RANGES)

        assert plan == MaterialPlan(6, 0, 6, 2, 3)

    def test_normal_n_over_90_rounds_up_to_three_multiple(self) -> None:
        plan = MaterialGroupRule().calculate(91, NORMAL_RANGES)

        assert plan == MaterialPlan(6, 0, 6, 2, 3)

    def test_test_group_under_20(self) -> None:
        plan = MaterialGroupRule().calculate(10, TEST_RANGES)

        assert plan == MaterialPlan(5, 0, 5, 2, 3)

    def test_test_group_over_20(self) -> None:
        plan = MaterialGroupRule().calculate(60, TEST_RANGES)

        assert plan == MaterialPlan(20, 0, 20, 7, 3)

    def test_test_group_fallback_without_ranges(self) -> None:
        plan = MaterialGroupRule().calculate(
            10, [_range(20, None, "TEST_GROUP_3", 3, 0)]
        )

        assert plan == MaterialPlan(5, 0, 5, 2, 3)

    def test_zero_material_returns_empty_plan(self) -> None:
        plan = MaterialGroupRule().calculate(0, NORMAL_RANGES)

        assert plan == MaterialPlan(0, 0, 0, 0, 0)


class TestTaskNameRule:
    """任务命名规则测试。"""

    def test_paid_name(self) -> None:
        name = TaskNameRule().build(
            "番茄",
            "我的剧",
            date(2026, 8, 7),
            datetime(2026, 8, 7, 10, 15, 30, tzinfo=UTC),
            "端付",
        )

        assert name == "番茄#端付我的剧20260807ubr-20260807-181530-1"

    def test_free_name(self) -> None:
        name = TaskNameRule().build(
            "番茄",
            "我的剧",
            date(2026, 8, 7),
            datetime(2026, 8, 7, 10, 15, 30, tzinfo=UTC),
            "端免",
        )

        assert name == "番茄#端免我的剧20260807bxr-20260807-181530-1"

    def test_test_name(self) -> None:
        name = TaskNameRule().build(
            "剧变",
            "短剧B",
            date(2026, 8, 7),
            datetime(2026, 8, 7, 10, 15, 30, tzinfo=UTC),
            "测试",
        )

        assert name == "剧变#测试短剧B20260807cbo-20260807-181530-1"

    def test_unknown_plan_type_raises(self) -> None:
        with pytest.raises(ValueError):
            TaskNameRule().build(
                "番茄", "我的剧", date(2026, 8, 7), datetime.now(UTC), "未知"
            )


class TestPlanSpecBuilder:
    """Builder 组合测试。"""

    def _task(self) -> DramaTask:
        return DramaTask(
            id="task-1",
            drama_name="我的剧",
            platform="番茄",
            available_time=datetime(2026, 8, 7, 10, 0, tzinfo=UTC),
        )

    def _accounts(self) -> list[dict]:
        return [
            {"role": "B1", "cid": "cid-b1"},
            {"role": "B4", "cid": "cid-b4"},
            {"role": "B7", "cid": "cid-b7"},
            {"role": "BX", "cid": "cid-bx"},
            {"role": "B1-9.9", "cid": "cid-iap-9-9"},
            {"role": "B2-2.9", "cid": "cid-iap-2-9"},
        ]

    def test_build_full_plan_spec(self) -> None:
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

        spec = builder.build(
            self._task(),
            links,
            self._accounts(),
            "product-1",
            20,
            NORMAL_RANGES,
            "v1",
        )

        assert spec.drama_name == "我的剧"
        assert spec.platform == "番茄"
        assert spec.link_set == links
        assert spec.account_cids == [
            "cid-b1",
            "cid-b4",
            "cid-b7",
            "cid-bx",
            "cid-iap-9-9",
            "cid-iap-2-9",
        ]
        assert spec.promotion_configs == {
            "IAA": "iaa-番茄-我的剧",
            "9.9": "9.9-番茄-我的剧",
            "2.9": "2.9-番茄-我的剧",
        }
        assert spec.material_groups == MaterialPlan(1, 2, 3, 1, 3)
        assert spec.expected_project_count == 3
        assert spec.rule_version == "v1"
        assert spec.product_id == "product-1"
        assert spec.task_name.startswith("番茄#端付我的剧20260807ubr-20260807-")
        assert spec.task_name.endswith("-1")

    def test_build_iaa_only_uses_free_name(self) -> None:
        builder = PlanSpecBuilder(
            AccountRoutingRule(),
            PromotionContentMappingRule(),
            MaterialGroupRule(),
            TaskNameRule(),
        )

        spec = builder.build(
            self._task(),
            {"IAA": "https://iaa/1"},
            self._accounts(),
            "product-1",
            20,
            NORMAL_RANGES,
            "v1",
        )

        assert spec.task_name.startswith("番茄#端免我的剧")

    def test_build_with_test_account_uses_test_name(self) -> None:
        accounts = self._accounts() + [
            {"role": "B4", "cid": "cid-test", "is_test": True}
        ]
        builder = PlanSpecBuilder(
            AccountRoutingRule(),
            PromotionContentMappingRule(),
            MaterialGroupRule(),
            TaskNameRule(),
        )

        spec = builder.build(
            self._task(),
            {"IAA": "https://iaa/1"},
            accounts,
            "product-1",
            20,
            NORMAL_RANGES,
            "v1",
            include_test=True,
        )

        assert spec.task_name.startswith("番茄#测试我的剧")
        assert "cid-test" in spec.account_cids

    def test_build_filters_blank_links(self) -> None:
        builder = PlanSpecBuilder(
            AccountRoutingRule(),
            PromotionContentMappingRule(),
            MaterialGroupRule(),
            TaskNameRule(),
        )

        spec = builder.build(
            self._task(),
            {"IAA": "https://iaa/1", "2.9": ""},
            self._accounts(),
            None,
            20,
            NORMAL_RANGES,
            "v1",
        )

        assert spec.link_set == {"IAA": "https://iaa/1"}
        assert spec.promotion_configs == {"IAA": "iaa-番茄-我的剧"}

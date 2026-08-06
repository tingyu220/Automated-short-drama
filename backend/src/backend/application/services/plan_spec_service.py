"""PlanSpec 生成服务：组合纯规则输出完整计划规格."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from backend.application.services.plan_rules import (
    LINK_TYPES,
    PLAN_TYPE_FREE,
    PLAN_TYPE_PAID,
    PLAN_TYPE_TEST,
)
from backend.domain.plans.plan_spec import PlanSpec

if TYPE_CHECKING:
    from backend.application.services.plan_rules import (
        AccountRoutingRule,
        MaterialGroupRule,
        PromotionContentMappingRule,
        TaskNameRule,
    )
    from backend.domain.rules.material_rule_range import MaterialRuleRange
    from backend.domain.tasks.drama_task import DramaTask


class PlanSpecBuilder:
    """按任务、链接、账户与规则数据生成 PlanSpec。"""

    def __init__(
        self,
        routing: AccountRoutingRule,
        mapping: PromotionContentMappingRule,
        material: MaterialGroupRule,
        naming: TaskNameRule,
    ) -> None:
        self._routing = routing
        self._mapping = mapping
        self._material = material
        self._naming = naming

    def build(
        self,
        task: DramaTask,
        links: dict[str, str],
        accounts: list[dict],
        product_id: str | None,
        material_count: int,
        material_ranges: list[MaterialRuleRange],
        rule_version: str | None,
        include_test: bool = False,
    ) -> PlanSpec:
        """生成链接集、账户映射、推广配置、素材分组与任务名称。"""
        link_set = {
            link_type: links[link_type]
            for link_type in LINK_TYPES
            if links.get(link_type)
        }
        link_types = set(link_set)

        routing_map = self._routing.build(link_types, accounts, include_test)
        account_cids = _dedupe(
            cid
            for link_type in LINK_TYPES
            for cid in routing_map.get(link_type, [])
        )
        promotion_configs = self._mapping.build(
            task.platform, task.drama_name, link_types
        )
        material_groups = self._material.calculate(
            material_count, list(material_ranges)
        )
        plan_type = self._primary_plan_type(link_types, include_test)
        task_name = self._naming.build(
            task.platform,
            task.drama_name,
            task.available_time.date(),
            datetime.now(timezone.utc),
            plan_type,
        )

        return PlanSpec(
            drama_name=task.drama_name,
            platform=task.platform,
            task_name=task_name,
            link_set=link_set,
            account_cids=account_cids,
            product_id=product_id,
            promotion_configs=promotion_configs,
            material_groups=material_groups,
            expected_project_count=material_groups.project_count,
            rule_version=rule_version,
        )

    @staticmethod
    def _primary_plan_type(link_types: set[str], include_test: bool) -> str:
        """测试 > 端付 > 端免 的主计划类型优先级。"""
        if include_test:
            return PLAN_TYPE_TEST
        if link_types & {"9.9", "2.9"}:
            return PLAN_TYPE_PAID
        return PLAN_TYPE_FREE


def _dedupe(values) -> list[str]:
    """按出现顺序去重，跨链接类型共用同一 CID 时只保留一次。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

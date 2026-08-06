"""PlanSpec 生成规则：纯函数、可注入、不依赖 SQLAlchemy."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from backend.domain.plans.plan_spec import MaterialPlan
from backend.domain.rules.material_rule_range import MaterialRuleRange

LINK_TYPES = ("IAA", "9.9", "2.9")

PLAN_TYPE_PAID = "端付"
PLAN_TYPE_FREE = "端免"
PLAN_TYPE_TEST = "测试"

_IAA_ROLES = {"B1", "B4", "B7", "BX"}
_TEST_STRATEGY_PREFIX = "TEST_"
_DEFAULT_GROUP_SIZE_CAP = 30
_NAME_MARKERS = {
    PLAN_TYPE_PAID: "ubr",
    PLAN_TYPE_FREE: "bxr",
    PLAN_TYPE_TEST: "cbo",
}


class AccountRoutingRule:
    """按链接类型与账户角色生成 CID 路由映射。"""

    def build(
        self,
        link_types: set[str],
        accounts: list[dict],
        include_test: bool,
    ) -> dict[str, list[str]]:
        """返回 {IAA: [cids], 9.9: [cids], 2.9: [cids]}，仅包含需要的链接类型。"""
        result: dict[str, list[str]] = {}
        if "IAA" in link_types:
            result["IAA"] = self._cids_by_roles(accounts, _IAA_ROLES)
            if include_test:
                result["IAA"] = self._append_test_account(result["IAA"], accounts)
        if "9.9" in link_types:
            result["9.9"] = self._cids_by_roles(accounts, {"B1-9.9"})
        if "2.9" in link_types:
            result["2.9"] = self._cids_by_roles(accounts, {"B2-2.9"})
        return result

    @staticmethod
    def _cids_by_roles(accounts: list[dict], roles: set[str]) -> list[str]:
        """按完整角色名精确匹配收集 CID，保持账户列表顺序并去重。"""
        cids: list[str] = []
        seen: set[str] = set()
        for account in accounts:
            role = str(account.get("role", ""))
            cid = str(account.get("cid", ""))
            if role in roles and cid and cid not in seen:
                seen.add(cid)
                cids.append(cid)
        return cids

    @staticmethod
    def _append_test_account(
        cids: list[str],
        accounts: list[dict],
    ) -> list[str]:
        """追加测试户 B4（优先标记 is_test 的账户），按 CID 去重。"""
        candidates = [
            account
            for account in accounts
            if str(account.get("role", "")).split("-")[0] == "B4"
        ]
        test_account = next(
            (
                account
                for account in candidates
                if account.get("is_test") is True
            ),
            candidates[0] if candidates else None,
        )
        if test_account is None:
            return list(cids)
        cid = str(test_account.get("cid", ""))
        if cid and cid not in cids:
            return [*cids, cid]
        return list(cids)


class PromotionContentMappingRule:
    """按链接类型生成推广内容配置名。"""

    _PREFIXES = {"IAA": "iaa", "9.9": "9.9", "2.9": "2.9"}

    def build(
        self,
        platform: str,
        drama_name: str,
        link_types: set[str],
    ) -> dict[str, str]:
        """返回 {链接类型: f"{prefix}-{platform}-{drama_name}"}。"""
        return {
            link_type: f"{self._PREFIXES[link_type]}-{platform}-{drama_name}"
            for link_type in LINK_TYPES
            if link_type in link_types
        }


class MaterialGroupRule:
    """素材分组规则：常规户按区间配置复制，测试户按条数分档。"""

    def calculate(
        self,
        material_count: int,
        ranges: list[MaterialRuleRange],
    ) -> MaterialPlan:
        """按 ranges 中是否存在测试策略区分常规/测试户分组。"""
        if material_count < 0:
            raise ValueError("material_count 不能为负数")
        if material_count == 0:
            return MaterialPlan(0, 0, 0, 0, 0)

        test_ranges = [
            rule
            for rule in ranges
            if rule.strategy.startswith(_TEST_STRATEGY_PREFIX)
        ]
        if test_ranges:
            return self._calculate_test(material_count, test_ranges)
        return self._calculate_normal(material_count, ranges)

    @staticmethod
    def _calculate_normal(
        material_count: int,
        ranges: list[MaterialRuleRange],
    ) -> MaterialPlan:
        """常规分组：命中区间按 base/copy，无命中按 <=30 均匀分 3 的倍数。"""
        match = _match_range(ranges, material_count)
        cap = max(
            (rule.group_size_cap for rule in ranges if rule.group_size_cap > 0),
            default=_DEFAULT_GROUP_SIZE_CAP,
        )
        if match is None:
            final_groups = _ceil_to_three_multiple(
                math.ceil(material_count / cap)
            )
            return MaterialPlan(
                base_groups=final_groups,
                copy_count=0,
                final_group_count=final_groups,
                ad_limit_per_project=final_groups // 3,
                project_count=3,
            )

        base_groups = max(match.base_group_count, 1)
        copy_count = max(match.copy_count, 0)
        match_cap = max(match.group_size_cap, 1)
        if math.ceil(material_count / base_groups) <= match_cap:
            final_groups = base_groups * (copy_count + 1)
        else:
            final_groups = _ceil_to_three_multiple(
                math.ceil(material_count / match_cap)
            )
        return MaterialPlan(
            base_groups=base_groups,
            copy_count=copy_count,
            final_group_count=final_groups,
            ad_limit_per_project=final_groups // 3,
            project_count=max(match.target_project_count, 1),
        )

    @staticmethod
    def _calculate_test(
        material_count: int,
        ranges: list[MaterialRuleRange],
    ) -> MaterialPlan:
        """测试户分组：每组 2/3 条不复制，ad_limit 按组数三档封顶 10。"""
        match = _match_range(ranges, material_count)
        if match is None:
            per_group = 2 if material_count < 20 else 3
        else:
            per_group = max(match.base_group_count, 1)
        groups = math.ceil(material_count / per_group)
        ad_limit = min(10, math.ceil(groups / 3))
        project_count = math.ceil(groups / ad_limit) if ad_limit else 0
        return MaterialPlan(
            base_groups=groups,
            copy_count=0,
            final_group_count=groups,
            ad_limit_per_project=ad_limit,
            project_count=project_count,
        )


class TaskNameRule:
    """任务命名规则：端付/端免/测试模板渲染。"""

    def build(
        self,
        platform: str,
        drama_name: str,
        date: date,
        now: datetime,
        plan_type: str,
    ) -> str:
        """按模板生成计划名，-1 为计划序号默认值。"""
        marker = _NAME_MARKERS.get(plan_type)
        if marker is None:
            raise ValueError(f"不支持的计划类型: {plan_type}")
        return (
            f"{platform}#{plan_type}{drama_name}"
            f"{date.strftime('%Y%m%d')}{marker}-"
            f"{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-1"
        )


def _match_range(
    ranges: list[MaterialRuleRange],
    material_count: int,
) -> MaterialRuleRange | None:
    """选择最具体的命中区间（min 最大者优先）。"""
    matches = [
        rule
        for rule in ranges
        if rule.min_material_count <= material_count
        and (
            rule.max_material_count is None
            or material_count <= rule.max_material_count
        )
    ]
    return max(matches, key=lambda rule: rule.min_material_count, default=None)


def _ceil_to_three_multiple(value: int) -> int:
    """返回不小于 value 的最小 3 的倍数。"""
    return math.ceil(value / 3) * 3

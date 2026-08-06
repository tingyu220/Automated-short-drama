"""PlanSpec 提交前校验服务：纯函数、可注入、不依赖 SQLAlchemy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from backend.domain.plans.plan_spec import PlanSpec

_NAME_MARKERS = ("ubr", "bxr", "cbo")
_LINK_TYPE_ROLES = {
    "9.9": ("B1-9.9", "9.9"),
    "2.9": ("B2-2.9", "2.9"),
}


@dataclass
class ValidationIssue:
    """单个校验问题。"""

    code: str
    message: str
    field: str


@dataclass
class ValidationReport:
    """校验汇总结果。"""

    passed: bool
    issues: list[ValidationIssue]


class PlanValidationService:
    """按提交前检查清单校验 PlanSpec 与 CID 配置。"""

    def __init__(
        self,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def validate(
        self,
        spec: PlanSpec,
        cid_configs: list[dict],
    ) -> ValidationReport:
        """校验 spec，cid_configs 为 CID 配置字典列表。"""
        now = self._now_provider()
        issues: list[ValidationIssue] = []
        issues.extend(self._check_link_set(spec))
        issues.extend(self._check_cid_configs(spec, cid_configs, now))
        issues.extend(self._check_template_accounts(spec, cid_configs, now))
        issues.extend(self._check_material_count(spec))
        issues.extend(self._check_task_name(spec))
        return ValidationReport(passed=not issues, issues=issues)

    @staticmethod
    def _check_link_set(spec: PlanSpec) -> list[ValidationIssue]:
        if spec.link_set:
            return []
        return [
            ValidationIssue(
                code="LINK_SET_EMPTY",
                message="链接集为空，至少需要一个有效投放链接",
                field="link_set",
            )
        ]

    def _check_cid_configs(
        self,
        spec: PlanSpec,
        cid_configs: list[dict],
        now: datetime,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for cid in spec.account_cids:
            matches = self._valid_configs_for(cid, cid_configs, now)
            if len(matches) != 1:
                issues.append(
                    ValidationIssue(
                        code="CID_CONFIG_MISSING",
                        message=(
                            f"账户 CID {cid} 缺少唯一有效配置"
                            f"（当前匹配 {len(matches)} 条）"
                        ),
                        field="account_cids",
                    )
                )
                continue
            config = matches[0]
            if not _non_empty(config.get("douyin_account")):
                issues.append(
                    ValidationIssue(
                        code="DOUYIN_ACCOUNT_EMPTY",
                        message=f"CID {cid} 的抖音账号为空",
                        field="cid_configs.douyin_account",
                    )
                )
            missing = [
                key
                for key in ("ad_preset", "account_open_preset")
                if not _non_empty(config.get(key))
            ]
            if missing:
                issues.append(
                    ValidationIssue(
                        code="PRESET_INCOMPLETE",
                        message=f"CID {cid} 预设不完整：{', '.join(missing)}",
                        field="cid_configs.presets",
                    )
                )
        return issues

    def _check_template_accounts(
        self,
        spec: PlanSpec,
        cid_configs: list[dict],
        now: datetime,
    ) -> list[ValidationIssue]:
        covered: set[str] = set()
        for cid in spec.account_cids:
            matches = self._valid_configs_for(cid, cid_configs, now)
            if len(matches) != 1:
                continue
            delivery_type = str(matches[0].get("delivery_type", ""))
            for link_type, roles in _LINK_TYPE_ROLES.items():
                if delivery_type in roles:
                    covered.add(link_type)

        issues: list[ValidationIssue] = []
        for link_type in _LINK_TYPE_ROLES:
            if link_type in spec.link_set and link_type not in covered:
                issues.append(
                    ValidationIssue(
                        code="TEMPLATE_ACCOUNT_MISMATCH",
                        message=(
                            f"{link_type} 链接存在但账户缺少"
                            f"{_LINK_TYPE_ROLES[link_type][0]} 角色 CID"
                        ),
                        field=f"link_set.{link_type}",
                    )
                )
        return issues

    @staticmethod
    def _check_material_count(spec: PlanSpec) -> list[ValidationIssue]:
        if spec.material_groups is not None and spec.expected_project_count > 0:
            return []
        return [
            ValidationIssue(
                code="MATERIAL_COUNT_INVALID",
                message=(
                    "素材分组为空或预期项目数无效"
                    f"（expected_project_count={spec.expected_project_count}）"
                ),
                field="material_groups",
            )
        ]

    @staticmethod
    def _check_task_name(spec: PlanSpec) -> list[ValidationIssue]:
        if spec.task_name and any(
            marker in spec.task_name for marker in _NAME_MARKERS
        ):
            return []
        return [
            ValidationIssue(
                code="TASK_NAME_INVALID",
                message="任务名称为空或缺少命名模板标记（ubr/bxr/cbo）",
                field="task_name",
            )
        ]

    @staticmethod
    def _valid_configs_for(
        cid: str,
        cid_configs: list[dict],
        now: datetime,
    ) -> list[dict]:
        """返回与 CID 匹配且主体/投放类型/启用/生效时间均有效的配置。"""
        return [
            config
            for config in cid_configs
            if str(config.get("cid", "")) == cid
            and _non_empty(config.get("subject"))
            and _non_empty(config.get("delivery_type"))
            and config.get("enabled") is True
            and _is_effective(config, now)
        ]


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_effective(config: dict, now: datetime) -> bool:
    effective_from = _as_aware_datetime(config.get("effective_from"))
    if effective_from is None or effective_from > now:
        return False
    effective_to = config.get("effective_to")
    if effective_to is not None:
        end = _as_aware_datetime(effective_to)
        if end is None or now > end:
            return False
    return True


def _as_aware_datetime(value: Any) -> datetime | None:
    """把 datetime 或 ISO 字符串归一化为带时区的 datetime。"""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

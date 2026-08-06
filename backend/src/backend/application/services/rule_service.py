"""规则配置服务：草稿/校验/模拟/发布/版本/快照/审计."""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.domain.errors.domain_error import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.domain.ports.repositories import (
    ChangeLogRepository,
    MaterialRuleRepository,
    PriceRuleRepository,
    RuleRepository,
    SnapshotRepository,
)
from backend.domain.rules.config_change_log import ConfigChangeLog
from backend.domain.rules.config_snapshot import ConfigSnapshot
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.rules.rule_set import RuleSet, RuleStatus
from backend.domain.rules.rule_version import RuleVersion, RuleVersionStatus
from backend.domain.rules.template_price_rule import TemplatePriceRule


@dataclass
class SimulationOutput:
    """单个价格候选的模拟匹配结果."""

    candidate: float
    matched_rule_key: str | None
    target_price: float | None
    distance: float | None
    selection_reason: str


@dataclass
class SimulationResult:
    """价格模拟结果集."""

    inputs: list[float]
    outputs: list[SimulationOutput] = field(default_factory=list)


_RULE_SET_FIELDS = ("key", "name", "category", "description")
_PENDING_STATUSES = (RuleVersionStatus.DRAFT, RuleVersionStatus.VALIDATING)


def create_draft(
    rule_repo: RuleRepository,
    key: str,
    name: str,
    category: str,
    description: str = "",
) -> RuleSet:
    """创建 DRAFT 规则集."""
    rule_set = RuleSet(
        id=str(uuid.uuid4()),
        key=key,
        name=name,
        category=category,
        description=description,
        status=RuleStatus.DRAFT,
    )
    return rule_repo.add_rule_set(rule_set)


def update_draft(
    rule_repo: RuleRepository,
    rule_set_id: str,
    changes: dict[str, Any],
) -> RuleSet:
    """更新 DRAFT 规则集，非 DRAFT 状态抛 ConflictError."""
    rule_set = rule_repo.get_rule_set(rule_set_id)
    if rule_set is None:
        raise NotFoundError(f"规则集不存在: {rule_set_id}")
    if rule_set.status != RuleStatus.DRAFT:
        raise ConflictError(
            f"规则集 {rule_set_id} 状态为 {rule_set.status}，仅 DRAFT 可编辑"
        )
    for field_name, value in changes.items():
        if field_name in _RULE_SET_FIELDS:
            setattr(rule_set, field_name, value)
    return rule_repo.update_rule_set(rule_set)


def save_draft_payload(
    rule_repo: RuleRepository,
    rule_set_id: str,
    payload: dict[str, Any],
) -> RuleVersion:
    """保存规则集草稿参数：更新最新 DRAFT 版本，缺失时创建。"""
    rule_set = rule_repo.get_rule_set(rule_set_id)
    if rule_set is None:
        raise NotFoundError(f"规则集不存在: {rule_set_id}")
    if rule_set.status != RuleStatus.DRAFT:
        raise ConflictError(
            f"规则集 {rule_set_id} 状态为 {rule_set.status}，仅 DRAFT 可编辑"
        )

    versions = rule_repo.list_rule_versions(rule_set_id)
    drafts = [v for v in versions if v.status == RuleVersionStatus.DRAFT]
    if drafts:
        latest = max(drafts, key=_version_sort_key)
        latest.payload_json = dict(payload)
        return rule_repo.update_rule_version(latest)

    version = RuleVersion(
        id=str(uuid.uuid4()),
        rule_set_id=rule_set_id,
        version=_next_version(versions),
        payload_json=dict(payload),
        status=RuleVersionStatus.DRAFT,
    )
    return rule_repo.add_rule_version(version)


def validate_rule(
    rule_repo: RuleRepository,
    price_repo: PriceRuleRepository,
    material_repo: MaterialRuleRepository,
    rule_set_id: str,
) -> RuleVersion:
    """校验价格与素材区间规则，通过后创建 VALIDATING 版本."""
    rule_set = rule_repo.get_rule_set(rule_set_id)
    if rule_set is None:
        raise NotFoundError(f"规则集不存在: {rule_set_id}")

    versions = rule_repo.list_rule_versions(rule_set_id)
    drafts = [v for v in versions if v.status == RuleVersionStatus.DRAFT]
    if not drafts:
        raise NotFoundError(f"规则集 {rule_set_id} 没有 DRAFT 版本可校验")
    latest_draft = max(drafts, key=_version_sort_key)

    errors = _validate_payload_draft(latest_draft.payload_json) or []
    errors.extend(_validate_price_rules(price_repo.list_template_price_rules()))
    errors.extend(
        _validate_material_rules(material_repo.list_material_rule_ranges())
    )
    if errors:
        raise ValidationError("规则校验失败", details={"errors": errors})

    version = RuleVersion(
        id=str(uuid.uuid4()),
        rule_set_id=rule_set_id,
        version=_next_version(versions),
        payload_json=dict(latest_draft.payload_json),
        status=RuleVersionStatus.VALIDATING,
    )
    return rule_repo.add_rule_version(version)


def _validate_payload_draft(payload: dict[str, Any]) -> list[str] | None:
    """校验草稿参数；草稿不含规则数据时返回 None 交给全局表校验。"""
    if not isinstance(payload, dict):
        return ["草稿 payload 必须是对象"]

    target = _pick(payload, "target_price", "targetPrice")
    minimum = _pick(payload, "min_price", "minPrice")
    maximum = _pick(payload, "max_price", "maxPrice")
    if (
        target is not None
        and minimum is not None
        and maximum is not None
    ):
        return _validate_price_items([payload])

    items = payload.get("price_rules") or payload.get("template_price_rules")
    if items is not None:
        if not isinstance(items, list):
            return ["price_rules 必须是列表"]
        return _validate_price_items(items)

    ranges = payload.get("material_ranges") or payload.get("ranges")
    if ranges is not None:
        if not isinstance(ranges, list):
            return ["material_ranges 必须是列表"]
        return _validate_material_items(ranges)

    return None


def _validate_price_items(items: list[dict]) -> list[str]:
    """校验草稿内价格规则项。"""
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append("价格规则项必须是对象")
            continue
        target = _pick(item, "target_price", "targetPrice")
        minimum = _pick(item, "min_price", "minPrice")
        maximum = _pick(item, "max_price", "maxPrice")
        if not all(
            isinstance(v, (int, float)) and math.isfinite(v)
            for v in (target, minimum, maximum)
        ):
            errors.append(f"价格规则 {_pick(item, 'key', 'id', '')} 含非数值")
            continue
        if minimum < 0 or maximum <= minimum:
            errors.append(
                f"价格规则 {_pick(item, 'key', 'id', '')} 区间非法: "
                f"min={minimum}, max={maximum}"
            )
            continue
        if not minimum <= target <= maximum:
            errors.append(
                f"价格规则 {_pick(item, 'key', 'id', '')} 目标价超出区间: "
                f"target={target}"
            )
    return errors


def _validate_material_items(items: list[dict]) -> list[str]:
    """校验草稿内素材区间项。"""
    errors: list[str] = []
    normalized: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append("素材区间项必须是对象")
            continue
        minimum = _pick(item, "min_material_count", "min")
        maximum = _pick(item, "max_material_count", "max")
        strategy = str(_pick(item, "strategy", "") or "")
        if (
            not isinstance(minimum, int)
            or (maximum is not None and not isinstance(maximum, int))
            or (maximum is not None and minimum >= maximum)
        ):
            errors.append(f"素材区间 {_pick(item, 'key', 'id', '')} 非法")
            continue
        normalized.append(
            {
                "key": str(_pick(item, "key", "id", "")),
                "min": minimum,
                "max": maximum,
                "strategy": strategy,
            }
        )

    by_strategy: dict[str, list[dict]] = {}
    for item in normalized:
        by_strategy.setdefault(item["strategy"], []).append(item)
    for strategy, ranges in by_strategy.items():
        ordered = sorted(ranges, key=lambda r: r["min"])
        for prev, current in zip(ordered, ordered[1:]):
            if prev["max"] is None or current["min"] <= prev["max"]:
                errors.append(
                    f"素材区间策略 {strategy} 重叠: "
                    f"{prev['key']} 与 {current['key']}"
                )
    return errors


def _pick(item: dict, *names: str) -> Any:
    """按多个候选键取第一个存在的值。"""
    for name in names:
        if name in item:
            return item[name]
    return None


def simulate_price(
    price_repo: PriceRuleRepository,
    candidates: list[float],
) -> SimulationResult:
    """按价格区间模拟 IAP 模板匹配与排序."""
    rules = [
        rule
        for rule in price_repo.list_template_price_rules()
        if rule.enabled
    ]
    outputs = [
        _simulate_candidate(candidate, rules) for candidate in candidates
    ]
    return SimulationResult(inputs=list(candidates), outputs=outputs)


def publish_version(
    rule_repo: RuleRepository,
    rule_set_id: str,
    actor: str = "system",
) -> RuleVersion:
    """发布最新 DRAFT/VALIDATING 版本并写入审计日志."""
    rule_set = rule_repo.get_rule_set(rule_set_id)
    if rule_set is None:
        raise NotFoundError(f"规则集不存在: {rule_set_id}")

    versions = rule_repo.list_rule_versions(rule_set_id)
    pending = [v for v in versions if v.status in _PENDING_STATUSES]
    if not pending:
        raise ConflictError(f"规则集 {rule_set_id} 没有待发布的版本")

    target = max(pending, key=_version_sort_key)
    previous_published = max(
        (
            v
            for v in versions
            if v.status == RuleVersionStatus.PUBLISHED and v.id != target.id
        ),
        key=_version_sort_key,
        default=None,
    )
    target.status = RuleVersionStatus.PUBLISHED
    target.published_at = datetime.now(timezone.utc)

    log = ConfigChangeLog(
        id=str(uuid.uuid4()),
        rule_set_id=rule_set_id,
        action="PUBLISH",
        actor=actor,
        from_version=previous_published.version if previous_published else None,
        to_version=target.version,
    )
    rule_repo.append_change_log(log)
    return rule_repo.update_rule_version(target)


def list_versions(
    rule_repo: RuleRepository,
    rule_set_id: str,
) -> list[RuleVersion]:
    """按创建时间倒序列出版本."""
    versions = rule_repo.list_rule_versions(rule_set_id)
    return sorted(versions, key=_version_sort_key, reverse=True)


def create_config_snapshot(
    snapshot_repo: SnapshotRepository,
    task_id: str,
    rule_version_id: str,
) -> ConfigSnapshot:
    """按已发布 RuleVersion 生成任务配置快照."""
    version = snapshot_repo.get_rule_version(rule_version_id)
    if version is None:
        raise NotFoundError(f"RuleVersion 不存在: {rule_version_id}")
    snapshot = ConfigSnapshot(
        id=str(uuid.uuid4()),
        task_id=task_id,
        rule_version_id=rule_version_id,
        snapshot_json=dict(version.payload_json),
    )
    return snapshot_repo.add(snapshot)


def log_change(
    log_repo: ChangeLogRepository,
    action: str,
    rule_set_id: str,
    from_version: str | None,
    to_version: str | None,
    actor: str,
    detail: dict | None = None,
) -> ConfigChangeLog:
    """写入配置变更审计日志."""
    log = ConfigChangeLog(
        id=str(uuid.uuid4()),
        rule_set_id=rule_set_id,
        action=action,
        from_version=from_version,
        to_version=to_version,
        actor=actor,
        detail_json=detail,
    )
    return log_repo.add(log)


def _version_sort_key(version: RuleVersion) -> tuple[datetime, int, str]:
    """版本排序键：时间优先，数值版本号其次."""
    number = int(version.version) if version.version.isdigit() else 0
    return (version.created_at, number, version.id)


def _next_version(versions: list[RuleVersion]) -> str:
    """取现有数值版本最大值 + 1."""
    numbers = [
        int(version.version)
        for version in versions
        if version.version.isdigit()
    ]
    return str((max(numbers) if numbers else 0) + 1)


def _validate_price_rules(rules: list[TemplatePriceRule]) -> list[str]:
    """校验价格规则：target/min/max 合法且 min <= target <= max."""
    errors: list[str] = []
    for rule in rules:
        if not rule.enabled:
            continue
        values = (rule.target_price, rule.min_price, rule.max_price)
        if not all(math.isfinite(value) for value in values):
            errors.append(f"价格规则 {rule.key or rule.id} 含非数值")
            continue
        if rule.min_price < 0 or rule.max_price <= rule.min_price:
            errors.append(
                f"价格规则 {rule.key or rule.id} 区间非法: "
                f"min={rule.min_price}, max={rule.max_price}"
            )
            continue
        if not rule.min_price <= rule.target_price <= rule.max_price:
            errors.append(
                f"价格规则 {rule.key or rule.id} 目标价超出区间: "
                f"target={rule.target_price}"
            )
    return errors


def _validate_material_rules(
    ranges: list[MaterialRuleRange],
) -> list[str]:
    """校验素材区间：min<max 且同策略区间不重叠."""
    errors: list[str] = []
    for item in ranges:
        if (
            item.max_material_count is not None
            and item.min_material_count >= item.max_material_count
        ):
            errors.append(
                f"素材区间 {item.id} 非法: "
                f"min={item.min_material_count}, "
                f"max={item.max_material_count}"
            )

    by_strategy: dict[str, list[MaterialRuleRange]] = {}
    for item in ranges:
        by_strategy.setdefault(item.strategy, []).append(item)
    for strategy, items in by_strategy.items():
        ordered = sorted(items, key=lambda r: r.min_material_count)
        for prev, current in zip(ordered, ordered[1:]):
            if _overlaps(prev, current):
                errors.append(
                    f"素材区间策略 {strategy} 重叠: "
                    f"{prev.id} 与 {current.id}"
                )
    return errors


def _overlaps(prev: MaterialRuleRange, current: MaterialRuleRange) -> bool:
    """判断两个同策略区间是否重叠（max=None 视为无上限）."""
    if prev.max_material_count is None:
        return True
    return current.min_material_count <= prev.max_material_count


def _simulate_candidate(
    candidate: float,
    rules: list[TemplatePriceRule],
) -> SimulationOutput:
    """匹配单个候选价格并输出排序结果."""
    matches = [
        rule
        for rule in rules
        if rule.min_price <= candidate <= rule.max_price
    ]
    if not matches:
        return SimulationOutput(
            candidate=candidate,
            matched_rule_key=None,
            target_price=None,
            distance=None,
            selection_reason="NO_MATCH",
        )

    def sort_key(rule: TemplatePriceRule) -> tuple[float, float, str]:
        return (
            abs(candidate - rule.target_price),
            -rule.target_price,
            rule.id,
        )

    best = min(matches, key=sort_key)
    return SimulationOutput(
        candidate=candidate,
        matched_rule_key=best.key,
        target_price=best.target_price,
        distance=abs(candidate - best.target_price),
        selection_reason="MATCHED_DISTANCE",
    )

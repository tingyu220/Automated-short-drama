"""默认规则 JSON 初始化导入服务.

只读导入 configs/defaults/rules.json，幂等写入规则配置表。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.domain.errors.domain_error import ConfigurationError
from backend.infrastructure.database.models.rule import (
    MaterialRuleRangeRecord,
    RuleParameterRecord,
    RuleSetRecord,
    RuleVersionRecord,
    TemplatePriceRuleRecord,
)

# defaults JSON 未提供该字段，按素材分组业务规则（区间上限 30）作为默认每组上限。
DEFAULT_GROUP_SIZE_CAP = 30


@dataclass(frozen=True)
class SeedResult:
    """默认规则导入统计。"""

    created_rules: int
    skipped_rules: int


def seed_rules_from_defaults(
    session: Session,
    defaults_path: Path,
    rule_repo: Any | None = None,
    price_repo: Any | None = None,
    material_repo: Any | None = None,
) -> SeedResult:
    """将 defaults JSON 导入规则配置表，已存在的 key 跳过。

    Args:
        session: SQLAlchemy Session；传入 repo 时仅作为事务容器使用。
        defaults_path: 默认规则 JSON 路径。
        rule_repo: 可选 rule_set/rule_version/rule_parameter 仓储（测试注入）。
        price_repo: 可选 template_price_rule 仓储（测试注入）。
        material_repo: 可选 material_rule_range 仓储（测试注入）。

    Returns:
        SeedResult 统计新增与跳过条数。

    Raises:
        ConfigurationError: 文件不存在、JSON 无效或结构不合法。
    """
    data = _load_defaults(defaults_path)
    created = 0
    skipped = 0

    for item in _as_list(data.get("rule_sets"), "rule_sets"):
        delta_created, delta_skipped = _seed_rule_set(session, item, rule_repo)
        created += delta_created
        skipped += delta_skipped

    for item in _as_list(data.get("template_price_rules"), "template_price_rules"):
        delta_created, delta_skipped = _seed_price_rule(session, item, price_repo)
        created += delta_created
        skipped += delta_skipped

    for item in _as_list(data.get("material_rule_ranges"), "material_rule_ranges"):
        delta_created, delta_skipped = _seed_material_rule(
            session, item, material_repo
        )
        created += delta_created
        skipped += delta_skipped

    return SeedResult(created_rules=created, skipped_rules=skipped)


def _load_defaults(defaults_path: Path) -> dict:
    """读取并解析 defaults JSON。"""
    path = Path(defaults_path)
    if not path.is_file():
        raise ConfigurationError(f"默认规则文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"默认规则 JSON 解析失败: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError(f"默认规则 JSON 顶层必须是对象: {path}")
    return data


def _as_list(value: object, section: str) -> list:
    """校验 defaults 分区为列表。"""
    if not isinstance(value, list):
        raise ConfigurationError(f"defaults 缺少 {section} 列表")
    return value


def _seed_rule_set(
    session: Session,
    item: dict,
    rule_repo: Any | None,
) -> tuple[int, int]:
    """导入单个 rule_set（含 rule_version 与 rule_parameter）。"""
    key = _require_str(item, "key")
    if _exists_rule_set(session, key, rule_repo):
        return 0, 1

    rule_set = RuleSetRecord(
        id=str(uuid.uuid4()),
        key=key,
        name=_require_str(item, "name"),
        category=_require_str(item, "category"),
        description=str(item.get("description", "")),
        status="DRAFT",
    )
    version = RuleVersionRecord(
        id=str(uuid.uuid4()),
        rule_set_id=rule_set.id,
        version=str(item.get("version", "1")),
        status="DRAFT",
        payload_json=json.dumps(_version_payload(item)),
    )

    if rule_repo is None:
        session.add(rule_set)
        session.flush()
        session.add(version)
        session.flush()
    else:
        rule_repo.add_rule_set(rule_set)
        rule_repo.add_rule_version(version)

    parameters = item.get("parameters") or []
    if not isinstance(parameters, list):
        raise ConfigurationError(f"rule_set {key} 的 parameters 必须是列表")
    for parameter in parameters:
        record = RuleParameterRecord(
            id=str(uuid.uuid4()),
            rule_version_id=version.id,
            name=_require_str(parameter, "name"),
            value_json=json.dumps(_require_value(parameter, "value")),
            data_type=_require_str(parameter, "data_type"),
            description=str(parameter.get("description", "")),
        )
        if rule_repo is None:
            session.add(record)
        else:
            rule_repo.add_rule_parameter(record)

    return 1, 0


def _seed_price_rule(
    session: Session,
    item: dict,
    price_repo: Any | None,
) -> tuple[int, int]:
    """导入单个 template_price_rule。"""
    key = _require_str(item, "key")
    if price_repo is None:
        exists = (
            session.query(TemplatePriceRuleRecord)
            .filter(TemplatePriceRuleRecord.key == key)
            .first()
            is not None
        )
    else:
        exists = price_repo.get_template_price_rule_by_key(key) is not None
    if exists:
        return 0, 1

    record = TemplatePriceRuleRecord(
        id=str(uuid.uuid4()),
        key=key,
        target_price=float(_require_value(item, "target_price")),
        min_price=float(_require_value(item, "min_price")),
        max_price=float(_require_value(item, "max_price")),
        same_distance_strategy=str(
            item.get("same_distance_strategy", "HIGHER_PRICE_FIRST")
        ),
        enabled=True,
    )
    if price_repo is None:
        session.add(record)
    else:
        price_repo.add_template_price_rule(record)
    return 1, 0


def _seed_material_rule(
    session: Session,
    item: dict,
    material_repo: Any | None,
) -> tuple[int, int]:
    """导入单个 material_rule_range。"""
    key = _require_str(item, "key")
    if material_repo is None:
        exists = (
            session.query(MaterialRuleRangeRecord)
            .filter(MaterialRuleRangeRecord.key == key)
            .first()
            is not None
        )
    else:
        exists = material_repo.get_material_rule_range_by_key(key) is not None
    if exists:
        return 0, 1

    raw_max = item.get("max_material_count")
    record = MaterialRuleRangeRecord(
        id=str(uuid.uuid4()),
        key=key,
        min_material_count=int(_require_value(item, "min_material_count")),
        max_material_count=int(raw_max) if raw_max is not None else None,
        strategy=_require_str(item, "strategy"),
        base_group_count=int(_require_value(item, "base_group_count")),
        copy_count=int(_require_value(item, "copy_count")),
        group_size_cap=DEFAULT_GROUP_SIZE_CAP,
        target_project_count=int(_require_value(item, "target_project_count")),
    )
    if material_repo is None:
        session.add(record)
    else:
        material_repo.add_material_rule_range(record)
    return 1, 0


def _exists_rule_set(
    session: Session,
    key: str,
    rule_repo: Any | None,
) -> bool:
    """判断 rule_set.key 是否已存在。"""
    if rule_repo is not None:
        return rule_repo.get_rule_set_by_key(key) is not None
    return (
        session.query(RuleSetRecord).filter(RuleSetRecord.key == key).first()
        is not None
    )


def _version_payload(item: dict) -> dict:
    """构造初始 RuleVersion payload：参数名到值的映射。"""
    parameters = item.get("parameters") or []
    if not isinstance(parameters, list):
        return {}
    return {
        _require_str(parameter, "name"): _require_value(parameter, "value")
        for parameter in parameters
    }


def _require_str(item: dict, field: str) -> str:
    """读取非空字符串字段，缺失或类型错误抛 ConfigurationError。"""
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"defaults 规则缺少字符串字段: {field}")
    return value


def _require_value(item: dict, field: str) -> object:
    """读取必填值字段，缺失抛 ConfigurationError。"""
    if field not in item:
        raise ConfigurationError(f"defaults 规则缺少字段: {field}")
    return item[field]

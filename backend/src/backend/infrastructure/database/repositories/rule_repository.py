"""规则配置仓储 SQLAlchemy 实现."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.rules.config_change_log import ConfigChangeLog
from backend.domain.rules.config_snapshot import ConfigSnapshot
from backend.domain.rules.material_rule_range import MaterialRuleRange
from backend.domain.rules.rule_set import RuleSet
from backend.domain.rules.rule_version import RuleVersion
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.infrastructure.database.models.rule import (
    ConfigChangeLogRecord,
    ConfigSnapshotRecord,
    MaterialRuleRangeRecord,
    RuleSetRecord,
    RuleVersionRecord,
    TemplatePriceRuleRecord,
)


class SqlAlchemyRuleRepository:
    """RuleRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_rule_set(self, rule_set: RuleSet) -> RuleSet:
        record = RuleSetRecord(
            id=rule_set.id,
            key=rule_set.key,
            name=rule_set.name,
            category=rule_set.category,
            description=rule_set.description,
            status=rule_set.status,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_rule_set(record)

    def get_rule_set(self, rule_set_id: str) -> RuleSet | None:
        record = self._session.get(RuleSetRecord, rule_set_id)
        return self._to_rule_set(record) if record else None

    def get_rule_set_by_key(self, key: str) -> RuleSet | None:
        record = (
            self._session.execute(
                select(RuleSetRecord)
                .where(RuleSetRecord.key == key)
                .order_by(RuleSetRecord.created_at)
            )
            .scalars()
            .first()
        )
        return self._to_rule_set(record) if record else None

    def list_rule_sets(self) -> list[RuleSet]:
        """按更新时间倒序列出全部规则集。"""
        records = (
            self._session.execute(
                select(RuleSetRecord).order_by(
                    RuleSetRecord.updated_at.desc(),
                    RuleSetRecord.id.desc(),
                )
            )
            .scalars()
            .all()
        )
        return [self._to_rule_set(record) for record in records]

    def update_rule_set(self, rule_set: RuleSet) -> RuleSet:
        record = self._session.get(RuleSetRecord, rule_set.id)
        if record is None:
            raise ValueError(f"RuleSet {rule_set.id} not found")
        record.key = rule_set.key
        record.name = rule_set.name
        record.category = rule_set.category
        record.description = rule_set.description
        record.status = rule_set.status
        self._session.flush()
        return self._to_rule_set(record)

    def add_rule_version(self, version: RuleVersion) -> RuleVersion:
        record = RuleVersionRecord(
            id=version.id,
            rule_set_id=version.rule_set_id,
            version=version.version,
            status=version.status,
            payload_json=json.dumps(version.payload_json, ensure_ascii=False),
            published_at=version.published_at,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_rule_version(record)

    def update_rule_version(self, version: RuleVersion) -> RuleVersion:
        record = self._session.get(RuleVersionRecord, version.id)
        if record is None:
            raise ValueError(f"RuleVersion {version.id} not found")
        record.status = version.status
        record.payload_json = json.dumps(version.payload_json, ensure_ascii=False)
        record.published_at = version.published_at
        self._session.flush()
        return self._to_rule_version(record)

    def list_rule_versions(self, rule_set_id: str) -> list[RuleVersion]:
        records = (
            self._session.execute(
                select(RuleVersionRecord)
                .where(RuleVersionRecord.rule_set_id == rule_set_id)
                .order_by(RuleVersionRecord.created_at)
            )
            .scalars()
            .all()
        )
        return [self._to_rule_version(record) for record in records]

    def get_rule_version(self, version_id: str) -> RuleVersion | None:
        record = self._session.get(RuleVersionRecord, version_id)
        return self._to_rule_version(record) if record else None

    def delete_rule_version(self, version_id: str) -> bool:
        """删除版本。"""
        record = self._session.get(RuleVersionRecord, version_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.flush()
        return True

    def append_change_log(self, log: ConfigChangeLog) -> ConfigChangeLog:
        record = ConfigChangeLogRecord(
            id=log.id,
            rule_set_id=log.rule_set_id,
            action=log.action,
            from_version=log.from_version,
            to_version=log.to_version,
            actor=log.actor,
            detail_json=(
                json.dumps(log.detail_json, ensure_ascii=False)
                if log.detail_json is not None
                else None
            ),
        )
        self._session.add(record)
        self._session.flush()
        return self._to_change_log(record)

    @staticmethod
    def _to_rule_set(record: RuleSetRecord) -> RuleSet:
        return RuleSet(
            id=record.id,
            key=record.key,
            name=record.name,
            category=record.category,
            description=record.description,
            status=record.status,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_rule_version(record: RuleVersionRecord) -> RuleVersion:
        return RuleVersion(
            id=record.id,
            rule_set_id=record.rule_set_id,
            version=record.version,
            status=record.status,
            payload_json=json.loads(record.payload_json),
            published_at=record.published_at,
            created_at=record.created_at,
        )

    @staticmethod
    def _to_change_log(record: ConfigChangeLogRecord) -> ConfigChangeLog:
        return ConfigChangeLog(
            id=record.id,
            rule_set_id=record.rule_set_id,
            action=record.action,
            from_version=record.from_version,
            to_version=record.to_version,
            actor=record.actor,
            detail_json=(
                json.loads(record.detail_json)
                if record.detail_json is not None
                else None
            ),
            changed_at=record.changed_at,
        )


class SqlAlchemyPriceRuleRepository:
    """PriceRuleRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_template_price_rules(self) -> list[TemplatePriceRule]:
        records = (
            self._session.execute(
                select(TemplatePriceRuleRecord).order_by(
                    TemplatePriceRuleRecord.created_at
                )
            )
            .scalars()
            .all()
        )
        return [self._to_domain(record) for record in records]

    def upsert_template_price_rule(self, rule: TemplatePriceRule) -> None:
        """按 key 覆盖价格规则；不存在时新增。"""
        record = (
            self._session.query(TemplatePriceRuleRecord)
            .filter(TemplatePriceRuleRecord.key == rule.key)
            .first()
        )
        if record is None:
            record = TemplatePriceRuleRecord(
                id=rule.id or str(uuid.uuid4()),
                key=rule.key,
                target_price=rule.target_price,
                min_price=rule.min_price,
                max_price=rule.max_price,
                same_distance_strategy=rule.same_distance_strategy,
                enabled=rule.enabled,
            )
            self._session.add(record)
        else:
            record.target_price = rule.target_price
            record.min_price = rule.min_price
            record.max_price = rule.max_price
            record.same_distance_strategy = rule.same_distance_strategy
            record.enabled = rule.enabled
        self._session.flush()

    def replace_template_price_rules(
        self, rules: list[TemplatePriceRule]
    ) -> None:
        """整体替换价格规则（发布时以版本 payload 全量为准）。"""
        self._session.query(TemplatePriceRuleRecord).delete()
        for rule in rules:
            record = TemplatePriceRuleRecord(
                id=rule.id or str(uuid.uuid4()),
                key=rule.key,
                target_price=rule.target_price,
                min_price=rule.min_price,
                max_price=rule.max_price,
                same_distance_strategy=rule.same_distance_strategy,
                enabled=rule.enabled,
            )
            self._session.add(record)
        self._session.flush()

    @staticmethod
    def _to_domain(record: TemplatePriceRuleRecord) -> TemplatePriceRule:
        return TemplatePriceRule(
            key=record.key,
            target_price=record.target_price,
            min_price=record.min_price,
            max_price=record.max_price,
            same_distance_strategy=record.same_distance_strategy,
            enabled=record.enabled,
            id=record.id,
            created_at=record.created_at,
        )


class SqlAlchemyMaterialRuleRepository:
    """MaterialRuleRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_material_rule_ranges(self) -> list[MaterialRuleRange]:
        records = (
            self._session.execute(
                select(MaterialRuleRangeRecord).order_by(
                    MaterialRuleRangeRecord.created_at
                )
            )
            .scalars()
            .all()
        )
        return [self._to_domain(record) for record in records]

    def replace_material_rule_ranges(self, ranges: list[MaterialRuleRange]) -> None:
        """整体替换素材区间规则（发布时以草稿全量为准）。"""
        self._session.query(MaterialRuleRangeRecord).delete()
        for item in ranges:
            record = MaterialRuleRangeRecord(
                id=item.id or str(uuid.uuid4()),
                key=item.key,
                min_material_count=item.min_material_count,
                max_material_count=item.max_material_count,
                strategy=item.strategy,
                base_group_count=item.base_group_count,
                copy_count=item.copy_count,
                group_size_cap=item.group_size_cap,
                target_project_count=item.target_project_count,
            )
            self._session.add(record)
        self._session.flush()

    @staticmethod
    def _to_domain(record: MaterialRuleRangeRecord) -> MaterialRuleRange:
        return MaterialRuleRange(
            min_material_count=record.min_material_count,
            max_material_count=record.max_material_count,
            strategy=record.strategy,
            base_group_count=record.base_group_count,
            copy_count=record.copy_count,
            group_size_cap=record.group_size_cap,
            target_project_count=record.target_project_count,
            key=record.key,
            id=record.id,
            created_at=record.created_at,
        )


class SqlAlchemySnapshotRepository:
    """SnapshotRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_rule_version(self, rule_version_id: str) -> RuleVersion | None:
        record = self._session.get(RuleVersionRecord, rule_version_id)
        if record is None:
            return None
        return RuleVersion(
            id=record.id,
            rule_set_id=record.rule_set_id,
            version=record.version,
            status=record.status,
            payload_json=json.loads(record.payload_json),
            published_at=record.published_at,
            created_at=record.created_at,
        )

    def add(self, snapshot: ConfigSnapshot) -> ConfigSnapshot:
        record = ConfigSnapshotRecord(
            id=snapshot.id,
            task_id=snapshot.task_id,
            rule_version_id=snapshot.rule_version_id,
            snapshot_json=json.dumps(snapshot.snapshot_json, ensure_ascii=False),
        )
        self._session.add(record)
        self._session.flush()
        return self._to_domain(record)

    def get_by_task(self, task_id: str) -> ConfigSnapshot | None:
        record = (
            self._session.execute(
                select(ConfigSnapshotRecord)
                .where(ConfigSnapshotRecord.task_id == task_id)
                .order_by(ConfigSnapshotRecord.created_at.desc())
            )
            .scalars()
            .first()
        )
        return self._to_domain(record) if record else None

    @staticmethod
    def _to_domain(record: ConfigSnapshotRecord) -> ConfigSnapshot:
        return ConfigSnapshot(
            id=record.id,
            task_id=record.task_id,
            rule_version_id=record.rule_version_id,
            snapshot_json=json.loads(record.snapshot_json),
            created_at=record.created_at,
        )


class SqlAlchemyChangeLogRepository:
    """ChangeLogRepository 协议的 SQLAlchemy 适配器."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, log: ConfigChangeLog) -> ConfigChangeLog:
        record = ConfigChangeLogRecord(
            id=log.id,
            rule_set_id=log.rule_set_id,
            action=log.action,
            from_version=log.from_version,
            to_version=log.to_version,
            actor=log.actor,
            detail_json=(
                json.dumps(log.detail_json, ensure_ascii=False)
                if log.detail_json is not None
                else None
            ),
        )
        self._session.add(record)
        self._session.flush()
        return SqlAlchemyRuleRepository._to_change_log(record)

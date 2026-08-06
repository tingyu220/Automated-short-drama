"""规则配置领域模型与 ORM 测试."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.domain.rules.platform_resource_config import PlatformResourceConfig
from backend.domain.rules.preset_mapping import PresetMapping
from backend.domain.rules.rule_set import RuleSet, RuleStatus
from backend.domain.rules.rule_version import RuleVersion, RuleVersionStatus
from backend.domain.rules.template_price_rule import TemplatePriceRule
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.models.rule import (
    ConfigChangeLogRecord,
    ConfigSnapshotRecord,
    DouyinAccountRecord,
    MaterialRuleRangeRecord,
    PlatformResourceConfigRecord,
    PresetMappingRecord,
    RuleParameterRecord,
    RuleSetRecord,
    RuleVersionRecord,
    TemplatePriceRuleRecord,
)


class TestRuleStatusConstants:
    """规则状态常量验证."""

    def test_rule_status_values(self):
        assert RuleStatus.DRAFT == "DRAFT"
        assert RuleStatus.VALIDATING == "VALIDATING"
        assert RuleStatus.PUBLISHED == "PUBLISHED"
        assert RuleStatus.ARCHIVED == "ARCHIVED"

    def test_rule_version_status_values(self):
        assert RuleVersionStatus.DRAFT == "DRAFT"
        assert RuleVersionStatus.VALIDATING == "VALIDATING"
        assert RuleVersionStatus.PUBLISHED == "PUBLISHED"
        assert RuleVersionStatus.ARCHIVED == "ARCHIVED"


class TestRuleSetDefaults:
    """RuleSet dataclass 默认值."""

    def test_default_status_and_id(self):
        rule_set = RuleSet(key="material", name="素材规则", category="MATERIAL")
        assert rule_set.status == RuleStatus.DRAFT
        assert rule_set.id == ""

    def test_default_description_empty(self):
        rule_set = RuleSet(key="material", name="素材规则", category="MATERIAL")
        assert rule_set.description == ""


class TestRuleVersionDefaults:
    """RuleVersion dataclass 默认值."""

    def test_default_status_and_id(self):
        version = RuleVersion(
            rule_set_id="rs1",
            version="v1",
            payload_json={"material_count": 30},
        )
        assert version.status == RuleVersionStatus.DRAFT
        assert version.id == ""

    def test_published_at_default_none(self):
        version = RuleVersion(
            rule_set_id="rs1",
            version="v1",
            payload_json={},
        )
        assert version.published_at is None


class TestTemplatePriceRuleDefaults:
    """TemplatePriceRule dataclass 默认值."""

    def test_same_distance_strategy_default(self):
        rule = TemplatePriceRule(target_price=2.9, min_price=2.6, max_price=5.0)
        assert rule.same_distance_strategy == "HIGHER_PRICE_FIRST"

    def test_enabled_default_true(self):
        rule = TemplatePriceRule(target_price=9.9, min_price=8.8, max_price=13.8)
        assert rule.enabled is True


class TestPresetMappingDefaults:
    """PresetMapping dataclass 默认值."""

    def test_enabled_default_true(self):
        mapping = PresetMapping(
            subject="主体A",
            delivery_type="IAP",
            cid="cid-1",
            ad_preset="预设A",
            douyin_account="B1",
            account_open_preset="开户A",
            effective_from=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
        assert mapping.enabled is True
        assert mapping.id == ""


class TestPlatformResourceConfigDefaults:
    """PlatformResourceConfig dataclass 默认值."""

    def test_enabled_default_true(self):
        config = PlatformResourceConfig(
            platform="TOMATO",
            key="poll_interval",
            value_json={"minutes": 5},
        )
        assert config.enabled is True
        assert config.id == ""


class TestMigrationTables:
    """Alembic upgrade head 后十张规则表存在."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.db_url = f"sqlite:///{db_path}"
        run_migrations(self.db_url)
        self.engine = create_app_engine(self.db_url)
        yield
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _table_exists(self, table_name: str) -> bool:
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            return row is not None

    def test_all_rule_tables_exist(self):
        for name in (
            "rule_set",
            "rule_version",
            "rule_parameter",
            "material_rule_range",
            "template_price_rule",
            "preset_mapping",
            "douyin_account",
            "platform_resource_config",
            "config_snapshot",
            "config_change_log",
        ):
            assert self._table_exists(name), f"{name} 表应存在"


class TestOrmWriteRead:
    """ORM 写入/读取规则配置核心记录."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            self.db_url, connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        yield
        self.session.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _add_rule_set(self, key: str = "material") -> RuleSetRecord:
        rule_set = RuleSetRecord(
            id=str(uuid.uuid4()),
            key=key,
            name="素材规则",
            category="MATERIAL",
            description="素材分组规则",
            status="DRAFT",
        )
        self.session.add(rule_set)
        self.session.flush()
        return rule_set

    def test_write_read_rule_set(self):
        record = self._add_rule_set()
        self.session.commit()
        fetched = self.session.get(RuleSetRecord, record.id)
        assert fetched is not None
        assert fetched.key == "material"
        assert fetched.name == "素材规则"
        assert fetched.category == "MATERIAL"
        assert fetched.status == "DRAFT"

    def test_write_read_rule_version(self):
        rule_set = self._add_rule_set()
        version_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = RuleVersionRecord(
            id=version_id,
            rule_set_id=rule_set.id,
            version="v1",
            status="PUBLISHED",
            payload_json='{"group_size_cap": 30}',
            published_at=now,
        )
        self.session.add(record)
        self.session.commit()
        fetched = self.session.get(RuleVersionRecord, version_id)
        assert fetched is not None
        assert fetched.rule_set_id == rule_set.id
        assert fetched.version == "v1"
        assert fetched.status == "PUBLISHED"
        assert fetched.payload_json == '{"group_size_cap": 30}'
        assert fetched.published_at is not None

    def test_write_read_template_price_rule(self):
        record_id = str(uuid.uuid4())
        record = TemplatePriceRuleRecord(
            id=record_id,
            target_price=2.9,
            min_price=2.6,
            max_price=5.0,
        )
        self.session.add(record)
        self.session.commit()
        fetched = self.session.get(TemplatePriceRuleRecord, record_id)
        assert fetched is not None
        assert fetched.target_price == 2.9
        assert fetched.min_price == 2.6
        assert fetched.max_price == 5.0
        assert fetched.same_distance_strategy == "HIGHER_PRICE_FIRST"
        assert fetched.enabled is True

    def test_write_read_preset_mapping(self):
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        record = PresetMappingRecord(
            id=record_id,
            subject="主体A",
            delivery_type="IAP",
            cid="cid-1",
            ad_preset="预设A",
            douyin_account="B1",
            account_open_preset="开户A",
            effective_from=now,
        )
        self.session.add(record)
        self.session.commit()
        fetched = self.session.get(PresetMappingRecord, record_id)
        assert fetched is not None
        assert fetched.subject == "主体A"
        assert fetched.delivery_type == "IAP"
        assert fetched.cid == "cid-1"
        assert fetched.ad_preset == "预设A"
        assert fetched.douyin_account == "B1"
        assert fetched.account_open_preset == "开户A"
        assert fetched.enabled is True

    def test_write_read_config_snapshot(self):
        rule_set = self._add_rule_set()
        version = RuleVersionRecord(
            id=str(uuid.uuid4()),
            rule_set_id=rule_set.id,
            version="v1",
            status="PUBLISHED",
            payload_json="{}",
        )
        self.session.add(version)
        self.session.flush()

        snapshot_id = str(uuid.uuid4())
        record = ConfigSnapshotRecord(
            id=snapshot_id,
            task_id="task-1",
            rule_version_id=version.id,
            snapshot_json='{"template_price": 2.9}',
        )
        self.session.add(record)
        self.session.commit()
        fetched = self.session.get(ConfigSnapshotRecord, snapshot_id)
        assert fetched is not None
        assert fetched.task_id == "task-1"
        assert fetched.rule_version_id == version.id
        assert fetched.snapshot_json == '{"template_price": 2.9}'

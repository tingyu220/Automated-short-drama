"""规则配置集成验收 —— 临时 SQLite + Alembic upgrade head + defaults seed."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.rule_service import (
    create_config_snapshot,
    publish_version,
    simulate_price,
    validate_rule,
)
from backend.domain.errors.domain_error import ValidationError
from backend.domain.rules.rule_version import RuleVersionStatus
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.models.rule import MaterialRuleRangeRecord
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
    SqlAlchemyRuleRepository,
    SqlAlchemySnapshotRepository,
)

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"


def _count_rows(session: Session, table_name: str) -> int:
    """统计临时 SQLite 表中行数。"""
    return session.execute(sa_text(f"SELECT count(*) FROM {table_name}")).scalar()


class TestRuleFullScenario:
    """规则配置完整集成验收场景。"""

    def test_full_rule_configuration_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                self._run_scenario(session)
            finally:
                session.close()
                engine.dispose()

    def _run_scenario(self, session: Session) -> None:
        """按验收顺序执行：seed -> 发布 -> 模拟 -> 快照 -> 隔离 -> 重叠校验。"""
        seed_rules_from_defaults(session, DEFAULTS_PATH)
        session.commit()

        # 1. seed 后规则配置三张核心表均存在
        assert _count_rows(session, "rule_set") == 3
        assert _count_rows(session, "rule_version") == 3
        assert _count_rows(session, "rule_parameter") == 7

        rule_repo = SqlAlchemyRuleRepository(session)
        price_repo = SqlAlchemyPriceRuleRepository(session)
        material_repo = SqlAlchemyMaterialRuleRepository(session)
        snapshot_repo = SqlAlchemySnapshotRepository(session)

        # 2. 两个 IAP 规则集 validate -> publish
        rule_2_9 = rule_repo.get_rule_set_by_key("iap_price_2_9")
        rule_9_9 = rule_repo.get_rule_set_by_key("iap_price_9_9")
        assert rule_2_9 is not None
        assert rule_9_9 is not None
        price_keys = {rule.key for rule in price_repo.list_template_price_rules()}
        assert {"iap_2_9", "iap_9_9"} <= price_keys

        validating_2_9 = validate_rule(
            rule_repo, price_repo, material_repo, rule_2_9.id
        )
        assert validating_2_9.status == RuleVersionStatus.VALIDATING
        published_2_9 = publish_version(rule_repo, rule_2_9.id, actor="tester")
        assert published_2_9.status == RuleVersionStatus.PUBLISHED
        assert published_2_9.published_at is not None
        published_2_9_id = published_2_9.id

        validating_9_9 = validate_rule(
            rule_repo, price_repo, material_repo, rule_9_9.id
        )
        assert validating_9_9.status == RuleVersionStatus.VALIDATING
        published_9_9 = publish_version(rule_repo, rule_9_9.id, actor="tester")
        assert published_9_9.status == RuleVersionStatus.PUBLISHED
        assert published_9_9.published_at is not None
        session.commit()

        # 3. 价格模拟：2.8/3.0/4.9 命中 2.9 规则，10.0 命中 9.9，6.0 无匹配
        result = simulate_price(price_repo, [2.8, 3.0, 4.9, 10.0, 6.0])
        assert [output.matched_rule_key for output in result.outputs] == [
            "iap_2_9",
            "iap_2_9",
            "iap_2_9",
            "iap_9_9",
            None,
        ]
        assert result.outputs[0].distance == pytest.approx(0.1)
        assert result.outputs[1].distance == pytest.approx(0.1)
        assert result.outputs[2].distance == pytest.approx(2.0)
        assert result.outputs[3].distance == pytest.approx(0.1)
        assert result.outputs[4].matched_rule_key is None
        assert result.outputs[4].selection_reason == "NO_MATCH"

        # 4. 按已发布版本生成任务快照并可查回
        task_id = str(uuid.uuid4())
        snapshot = create_config_snapshot(snapshot_repo, task_id, published_2_9_id)
        session.commit()
        old_payload = {"target_price": 2.9, "min_price": 2.6, "max_price": 5.0}

        fetched = snapshot_repo.get_by_task(task_id)
        assert fetched is not None
        assert fetched.id == snapshot.id
        assert fetched.rule_version_id == published_2_9_id
        assert fetched.snapshot_json == old_payload

        # 5. 再次发布新版本后，运行中任务的旧快照保持不变
        draft = next(
            version
            for version in rule_repo.list_rule_versions(rule_2_9.id)
            if version.status == RuleVersionStatus.DRAFT
        )
        new_payload = {"target_price": 3.9, "min_price": 3.6, "max_price": 5.5}
        draft.payload_json = new_payload
        rule_repo.update_rule_version(draft)

        validating_v3 = validate_rule(
            rule_repo, price_repo, material_repo, rule_2_9.id
        )
        assert validating_v3.payload_json == new_payload
        publish_version(rule_repo, rule_2_9.id, actor="tester")
        session.commit()

        fetched_again = snapshot_repo.get_by_task(task_id)
        assert fetched_again is not None
        assert fetched_again.id == snapshot.id
        assert fetched_again.rule_version_id == published_2_9_id
        assert fetched_again.snapshot_json == old_payload

        # 6. 插入同策略重叠区间后 validate 抛 ValidationError 且不新增版本
        session.add(
            MaterialRuleRangeRecord(
                id=str(uuid.uuid4()),
                key="overlap_acceptance",
                min_material_count=20,
                max_material_count=50,
                strategy="BASE_1_COPY_2",
                base_group_count=1,
                copy_count=2,
                group_size_cap=30,
                target_project_count=3,
            )
        )
        session.commit()

        version_count_before = len(rule_repo.list_rule_versions(rule_9_9.id))
        with pytest.raises(ValidationError):
            validate_rule(rule_repo, price_repo, material_repo, rule_9_9.id)
        assert len(rule_repo.list_rule_versions(rule_9_9.id)) == version_count_before

"""rule_service 集成测试 —— 临时 SQLite + Alembic + defaults seed."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.rule_service import (
    create_config_snapshot,
    list_versions,
    publish_version,
    simulate_price,
    validate_rule,
)
from backend.domain.rules.rule_set import RuleStatus
from backend.domain.rules.rule_version import RuleVersionStatus
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
    SqlAlchemyRuleRepository,
    SqlAlchemySnapshotRepository,
)

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"


class TestRuleServiceIntegration:
    """规则服务在真实 SQLite 上的端到端验证。"""

    def test_iap_rule_validate_publish_simulate_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                seed_rules_from_defaults(session, DEFAULTS_PATH)
                session.commit()

                rule_repo = SqlAlchemyRuleRepository(session)
                price_repo = SqlAlchemyPriceRuleRepository(session)
                material_repo = SqlAlchemyMaterialRuleRepository(session)
                snapshot_repo = SqlAlchemySnapshotRepository(session)

                rule_set = rule_repo.get_rule_set_by_key("iap_price_2_9")
                assert rule_set is not None
                assert rule_set.status == RuleStatus.DRAFT

                validating = validate_rule(
                    rule_repo, price_repo, material_repo, rule_set.id
                )
                assert validating.status == RuleVersionStatus.VALIDATING
                assert validating.version == "2"
                assert validating.payload_json == {
                    "target_price": 2.9,
                    "min_price": 2.6,
                    "max_price": 5.0,
                }

                published = publish_version(rule_repo, rule_set.id, actor="tester")
                assert published.status == RuleVersionStatus.PUBLISHED
                assert published.published_at is not None

                versions = list_versions(rule_repo, rule_set.id)
                assert [v.status for v in versions] == [
                    RuleVersionStatus.PUBLISHED,
                    RuleVersionStatus.DRAFT,
                ]
                assert versions[0].id == published.id

                result = simulate_price(price_repo, [2.9, 9.9, 100.0])
                assert [o.matched_rule_key for o in result.outputs] == [
                    "iap_2_9",
                    "iap_9_9",
                    None,
                ]
                assert result.outputs[0].distance == 0.0
                assert result.outputs[2].selection_reason == "NO_MATCH"

                task_id = str(uuid.uuid4())
                snapshot = create_config_snapshot(
                    snapshot_repo, task_id, published.id
                )
                session.commit()

                fetched = snapshot_repo.get_by_task(task_id)
                assert fetched is not None
                assert fetched.id == snapshot.id
                assert fetched.rule_version_id == published.id
                assert fetched.snapshot_json == {
                    "target_price": 2.9,
                    "min_price": 2.6,
                    "max_price": 5.0,
                }

                log_count = session.execute(
                    sa_text(
                        "SELECT count(*) FROM config_change_log "
                        "WHERE rule_set_id=:rid"
                    ),
                    {"rid": rule_set.id},
                ).scalar()
                assert log_count == 1
            finally:
                session.close()
                engine.dispose()

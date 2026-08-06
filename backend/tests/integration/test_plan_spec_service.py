"""PlanSpec 生成服务集成测试 —— 临时 SQLite + seed 规则 + Mock 账户."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.application.services.plan_rules import (
    AccountRoutingRule,
    MaterialGroupRule,
    PromotionContentMappingRule,
    TaskNameRule,
)
from backend.application.services.plan_spec_service import PlanSpecBuilder
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.models.rule import MaterialRuleRangeRecord
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
)

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"
UTC = timezone.utc


class TestPlanSpecServiceIntegration:
    """PlanSpec 服务在真实 SQLite + seed 规则上的端到端验证。"""

    def test_build_plan_spec_from_seeded_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                seed_rules_from_defaults(session, DEFAULTS_PATH)
                session.commit()

                material_repo = SqlAlchemyMaterialRuleRepository(session)
                ranges = material_repo.list_material_rule_ranges()
                strategies = {rule.strategy for rule in ranges}
                assert {"BASE_1_COPY_2", "BASE_2_COPY_2"} <= strategies

                task = DramaTask(
                    id="task-1",
                    drama_name="我的剧",
                    platform="番茄",
                    available_time=datetime(2026, 8, 7, 10, 0, tzinfo=UTC),
                )
                links = {
                    "IAA": "https://iaa/1",
                    "9.9": "https://iap/9.9",
                    "2.9": "https://iap/2.9",
                }
                accounts = [
                    {"role": "B1", "cid": "cid-iaa-b1"},
                    {"role": "B4", "cid": "cid-iaa-b4"},
                    {"role": "B7", "cid": "cid-iaa-b7"},
                    {"role": "BX", "cid": "cid-iaa-bx"},
                    {"role": "B1-9.9", "cid": "cid-iap-9-9"},
                    {"role": "B2-2.9", "cid": "cid-iap-2-9"},
                    {"role": "B4", "cid": "cid-test", "is_test": True},
                ]
                builder = PlanSpecBuilder(
                    AccountRoutingRule(),
                    PromotionContentMappingRule(),
                    MaterialGroupRule(),
                    TaskNameRule(),
                )

                spec = builder.build(
                    task,
                    links,
                    accounts,
                    "product-1",
                    20,
                    ranges,
                    "v1",
                    include_test=True,
                )

                assert spec.link_set == links
                assert spec.account_cids == [
                    "cid-iaa-b1",
                    "cid-iaa-b4",
                    "cid-iaa-b7",
                    "cid-iaa-bx",
                    "cid-test",
                    "cid-iap-9-9",
                    "cid-iap-2-9",
                ]
                assert spec.promotion_configs == {
                    "IAA": "iaa-番茄-我的剧",
                    "9.9": "9.9-番茄-我的剧",
                    "2.9": "2.9-番茄-我的剧",
                }
                assert spec.material_groups is not None
                assert spec.material_groups.final_group_count == 7
                assert spec.material_groups.ad_limit_per_project == 3
                assert spec.material_groups.project_count == 3
                assert spec.expected_project_count == 3
                assert spec.rule_version == "v1"
                assert spec.task_name.startswith("番茄#测试我的剧")
                assert spec.task_name.endswith("-1")
                normal_ranges = [
                    rule
                    for rule in ranges
                    if not rule.strategy.startswith("TEST_")
                ]
                assert MaterialGroupRule().calculate(70, normal_ranges).final_group_count == 6
                assert MaterialGroupRule().calculate(20, ranges).final_group_count == 7
            finally:
                session.close()
                engine.dispose()

    def test_material_group_rule_reads_seeded_test_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            session = Session(engine)
            try:
                seed_rules_from_defaults(session, DEFAULTS_PATH)
                session.add(
                    MaterialRuleRangeRecord(
                        id=str(uuid.uuid4()),
                        key="test_group_2",
                        min_material_count=0,
                        max_material_count=19,
                        strategy="TEST_GROUP_2",
                        base_group_count=2,
                        copy_count=0,
                        group_size_cap=30,
                        target_project_count=1,
                    )
                )
                session.commit()

                ranges = SqlAlchemyMaterialRuleRepository(
                    session
                ).list_material_rule_ranges()

                plan = MaterialGroupRule().calculate(10, ranges)

                assert plan.final_group_count == 5
                assert plan.ad_limit_per_project == 2
                assert plan.project_count == 3
            finally:
                session.close()
                engine.dispose()

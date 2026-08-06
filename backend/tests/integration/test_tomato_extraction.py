"""番茄提取服务集成测试：临时 DB + seed + 已发布价格规则 + MockTomatoAdapter."""
from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.rule_service import publish_version, validate_rule
from backend.application.services.tomato_extraction_service import scan_iap
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
    SqlAlchemyRuleRepository,
)
from backend.platforms.mock.mock_tomato import MockTomatoAdapter

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"


class TestTomatoExtractionIntegration:
    """scan_iap 与已发布价格规则、MockTomatoAdapter 的集成验收。"""

    def test_scan_iap_uses_published_rules_and_mock_links(self) -> None:
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
                for key in ("iap_price_2_9", "iap_price_9_9"):
                    rule_set = rule_repo.get_rule_set_by_key(key)
                    assert rule_set is not None
                    validate_rule(rule_repo, price_repo, material_repo, rule_set.id)
                    publish_version(rule_repo, rule_set.id, actor="tester")
                session.commit()

                rules = price_repo.list_template_price_rules()
                result = scan_iap("剧A", MockTomatoAdapter(), rules)

                assert result.business_result == "BOTH_AVAILABLE"
                assert result.iaa_link.link_type == "IAA"
                assert result.iaa_link.source_entry == "FREE"
                assert result.iap_2_9_link is not None
                assert result.iap_2_9_link.link_type == "IAP"
                assert result.iap_2_9_link.source_platform == "TOMATO"
                assert result.iap_2_9_link.source_entry == "PAID"
                assert result.iap_2_9_link.acquisition_method == "MOCK"
                assert result.iap_2_9_link.source_column == "K"
                assert result.iap_2_9_link.link_status == "OK"
                assert result.iap_9_9_link is not None
                assert result.iap_9_9_link.promotion_url.endswith("tpl-剧A-9-9")
                assert [
                    template.template_id for template in result.matched_templates
                ] == ["tpl-剧A-2-9", "tpl-剧A-9-9"]
            finally:
                session.close()
                engine.dispose()

"""完整 Dry Run 工作流集成测试：临时 DB + seed + Mock 适配器。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.application.services.dry_run_workflow import (
    COMPLETED,
    MANUAL_REVIEW,
    DryRunWorkflow,
)
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.rule_service import publish_version, validate_rule
from backend.domain.errors.domain_error import NotFoundError
from backend.domain.tasks.drama_task import DramaTask
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.repositories.rule_repository import (
    SqlAlchemyMaterialRuleRepository,
    SqlAlchemyPriceRuleRepository,
    SqlAlchemyRuleRepository,
)
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"
FULL_STEP_ORDER = [
    "LINK_EXTRACTION",
    "DRAMA_ASSET",
    "PROMOTION_CONFIG",
    "PRODUCT",
    "PLAN_SPEC",
    "SUBMIT",
    "POLL",
]


@pytest.fixture()
def price_rules():
    """临时 DB + seed + 发布价格规则，返回已发布价格规则列表。"""
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
            yield price_repo.list_template_price_rules()
        finally:
            session.close()
            engine.dispose()


class CountingFeishuAdapter(MockFeishuAdapter):
    """记录飞书写调用次数的观察 Mock。"""

    def __init__(self) -> None:
        super().__init__()
        self.write_links_calls = 0
        self.write_completion_calls = 0

    def write_links(self, task_id: str, links: dict[str, str]) -> None:
        self.write_links_calls += 1
        super().write_links(task_id, links)

    def write_completion(self, task_id: str) -> None:
        self.write_completion_calls += 1
        super().write_completion(task_id)


class NotFoundTomatoAdapter(MockTomatoAdapter):
    """模拟番茄未找到剧目。"""

    def extract_iaa_link(
        self,
        drama_name: str,
        episode_count: int,
        selected_episode: int,
    ):
        raise NotFoundError(f"番茄未找到剧目: {drama_name}")


def _tomato_task() -> DramaTask:
    return DramaTask(
        id="task-tomato-001",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )


def _jubian_task() -> DramaTask:
    return DramaTask(
        id="task-jubian-002",
        drama_name="剧B",
        platform="JUBIAN",
        available_time=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )


class TestDryRunWorkflowIntegration:
    """Mock 全链路 Dry Run 验收。"""

    def test_tomato_full_success(self, price_rules) -> None:
        delivery = MockDeliverySystemAdapter()
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            price_rules,
            allow_final_submit=True,
            use_real_adapters=True,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1", "cid-2"],
        )

        assert result.final_status == COMPLETED
        assert [step.step for step in result.steps] == FULL_STEP_ORDER
        assert all(step.status == "OK" for step in result.steps)
        assert result.links == {
            "IAA": "mock://iaa/剧A?ep=1",
            "2.9": "mock://iap/IAP/剧A?tpl=tpl-剧A-2-9",
            "9.9": "mock://iap/IAP/剧A?tpl=tpl-剧A-9-9",
        }
        assert result.asset is not None
        assert result.asset.drama_name == "剧A"
        assert result.plan_spec is not None
        assert result.plan_spec.task_name == "DRY-TOMATO-剧A"
        assert result.plan_spec.link_set == result.links
        assert result.plan_spec.account_cids == ["cid-1", "cid-2"]
        assert result.plan_spec.product_id
        assert result.external_task_id.startswith("task-")

    def test_jubian_uses_existing_links(self, price_rules) -> None:
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            MockDeliverySystemAdapter(),
            MockOceanEngineAdapter(),
            price_rules,
            allow_final_submit=True,
            use_real_adapters=True,
        )
        jubian_links = {
            "IAA": "mock://jubian/剧B/iaa",
            "2.9": None,
            "9.9": "mock://jubian/剧B/9.9",
        }

        result = workflow.run(
            _jubian_task(),
            episode_count=40,
            account_cids=["cid-3"],
            jubian_links=jubian_links,
        )

        assert result.final_status == COMPLETED
        assert [step.step for step in result.steps] == FULL_STEP_ORDER
        assert result.links == {
            "IAA": "mock://jubian/剧B/iaa",
            "9.9": "mock://jubian/剧B/9.9",
        }
        assert result.asset is not None
        assert result.asset.link == "mock://jubian/剧B/iaa"
        assert result.plan_spec is not None
        assert result.plan_spec.platform == "JUBIAN"
        assert result.plan_spec.task_name == "DRY-JUBIAN-剧B"
        assert result.external_task_id.startswith("task-")

    def test_tomato_not_found_stops_before_submit(self, price_rules) -> None:
        delivery = MockDeliverySystemAdapter()
        workflow = DryRunWorkflow(
            NotFoundTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            price_rules,
            allow_final_submit=True,
            use_real_adapters=True,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == MANUAL_REVIEW
        assert [step.step for step in result.steps] == ["LINK_EXTRACTION"]
        assert result.steps[0].status == "FAILED"
        assert result.steps[0].error_code == "NOT_FOUND"
        assert result.links == {}
        assert result.asset is None
        assert result.plan_spec is None
        assert result.external_task_id == ""

    def test_dry_run_never_writes_feishu(self, price_rules) -> None:
        feishu = CountingFeishuAdapter()
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            MockDeliverySystemAdapter(),
            MockOceanEngineAdapter(),
            price_rules,
            allow_final_submit=True,
            use_real_adapters=True,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == COMPLETED
        assert feishu.write_links_calls == 0
        assert feishu.write_completion_calls == 0
        assert feishu.written_links == {}

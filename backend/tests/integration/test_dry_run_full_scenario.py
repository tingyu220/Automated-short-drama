"""Dry Run 全场景验收：临时 DB + seed + Mock adapters。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from backend.application.services.dry_run_workflow import (
    COMPLETED,
    MANUAL_REVIEW,
    DryRunWorkflow,
)
from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.application.services.rule_service import publish_version, validate_rule
from backend.domain.errors.domain_error import ExternalAdapterError, NotFoundError
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


class RecordingFeishuAdapter(MockFeishuAdapter):
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


class RecordingDeliveryAdapter(MockDeliverySystemAdapter):
    """记录推广配置与提交计划链接集合的观察 Mock。"""

    def __init__(self) -> None:
        super().__init__()
        self.config_ids: list[str] = []
        self.config_link_types: list[str] = []
        self.submitted_link_sets: list[dict[str, str]] = []

    def ensure_promotion_config(self, asset_id: str, link_type: str, link: str) -> str:
        config_id = super().ensure_promotion_config(asset_id, link_type, link)
        self.config_ids.append(config_id)
        self.config_link_types.append(link_type)
        return config_id

    def submit_plan(self, plan_spec: Any) -> str:
        self.submitted_link_sets.append(dict(plan_spec.link_set))
        return super().submit_plan(plan_spec)


class NotFoundTomatoAdapter(MockTomatoAdapter):
    """模拟番茄未找到剧目。"""

    def extract_iaa_link(
        self,
        drama_name: str,
        episode_count: int,
        selected_episode: int,
    ):
        raise NotFoundError(f"番茄未找到剧目: {drama_name}")


class NoIapTomatoAdapter(MockTomatoAdapter):
    """模拟 IAP 无匹配模板，只保留 IAA。"""

    def scan_iap_templates(self, drama_name: str) -> list:
        return []


class PageChangedDeliveryAdapter(MockDeliverySystemAdapter):
    """模拟投放页面在资源步骤发生变化。"""

    def find_or_create_drama_asset(self, drama_name: str, link: str):
        raise ExternalAdapterError(
            "投放页面已变化，需人工确认",
            code="PAGE_CHANGED",
        )


def _tomato_task() -> DramaTask:
    return DramaTask(
        id="task-tomato-full-001",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )


class TestDryRunFullScenario:
    """Dry Run 全场景验收。"""

    def test_tomato_full_success(self, price_rules) -> None:
        feishu = RecordingFeishuAdapter()
        delivery = RecordingDeliveryAdapter()
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            price_rules,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1", "cid-2"],
        )

        assert result.final_status == COMPLETED
        assert result.links
        assert all(link.startswith("mock://") for link in result.links.values())
        assert result.asset is not None
        assert result.asset.delivery_drama_id
        assert delivery.config_ids
        assert delivery.config_link_types == ["IAA", "2.9", "9.9"]
        assert result.plan_spec is not None
        assert result.plan_spec.product_id
        assert result.external_task_id
        assert feishu.write_links_calls == 0
        assert feishu.write_completion_calls == 0
        assert feishu.written_links == {}

    def test_retry_after_not_found_recovers(self, price_rules) -> None:
        workflow = DryRunWorkflow(
            NotFoundTomatoAdapter(),
            MockDeliverySystemAdapter(),
            MockOceanEngineAdapter(),
            price_rules,
        )
        task = _tomato_task()

        first = workflow.run(task, episode_count=40, account_cids=["cid-1"])

        assert first.final_status == MANUAL_REVIEW
        assert first.steps[0].step == "LINK_EXTRACTION"
        assert first.steps[0].status == "FAILED"
        assert first.steps[0].error_code == "NOT_FOUND"

        # 同一工作流替换为可用 adapter 后重跑，应恢复为 COMPLETED。
        workflow._tomato = MockTomatoAdapter()
        second = workflow.run(task, episode_count=40, account_cids=["cid-1"])

        assert second.final_status == COMPLETED
        assert second.external_task_id
        assert all(step.status == "OK" for step in second.steps)

    def test_iap_no_template_skips_iap(self, price_rules) -> None:
        delivery = RecordingDeliveryAdapter()
        workflow = DryRunWorkflow(
            NoIapTomatoAdapter(),
            delivery,
            MockOceanEngineAdapter(),
            price_rules,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == COMPLETED
        assert result.links == {"IAA": "mock://iaa/剧A?ep=1"}
        assert delivery.config_link_types == ["IAA"]
        assert result.plan_spec is not None
        assert result.plan_spec.link_set == result.links
        assert delivery.submitted_link_sets == [{"IAA": "mock://iaa/剧A?ep=1"}]

    def test_page_changed_stops_at_asset_step(self, price_rules) -> None:
        workflow = DryRunWorkflow(
            MockTomatoAdapter(),
            PageChangedDeliveryAdapter(),
            MockOceanEngineAdapter(),
            price_rules,
        )

        result = workflow.run(
            _tomato_task(),
            episode_count=40,
            account_cids=["cid-1"],
        )

        assert result.final_status == MANUAL_REVIEW
        asset_step = next(
            step for step in result.steps if step.step == "DRAMA_ASSET"
        )
        assert asset_step.status == "FAILED"
        assert asset_step.error_code == "PAGE_CHANGED"
        assert result.asset is None
        assert result.plan_spec is None
        assert result.external_task_id == ""

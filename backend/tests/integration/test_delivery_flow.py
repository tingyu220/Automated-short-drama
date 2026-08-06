"""投放/巨量模拟服务集成测试：临时 DB + Mock 适配器全流程。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from backend.application.services.delivery_flow_service import DeliveryFlowService
from backend.domain.plans.plan_spec import PlanSpec
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter


class TestDeliveryFlowIntegration:
    """Mock 投放/巨量全链路验收。"""

    def test_full_mock_flow(self) -> None:
        links = {
            "IAA": "mock://iaa/剧A?ep=1",
            "2.9": "mock://iap/剧A?tpl=2-9",
            "9.9": "mock://iap/剧A?tpl=9-9",
        }
        cids = ["cid-b1-1", "cid-b4-1", "cid-b7-1", "cid-bx-1"]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{Path(tmpdir) / 'test.db'}"
            run_migrations(db_url)
            engine = create_app_engine(db_url)
            try:
                delivery = MockDeliverySystemAdapter(poll_rounds_before_completed=1)
                ocean = MockOceanEngineAdapter()
                service = DeliveryFlowService(delivery, ocean)

                asset = service.ensure_drama_asset("剧A", links["IAA"])
                assert asset.drama_name == "剧A"
                assert asset.link == links["IAA"]
                assert service.ensure_drama_asset("剧A", links["IAA"]) == asset

                config_ids = {
                    link_type: service.ensure_promotion_config(asset, link_type, link)
                    for link_type, link in links.items()
                }
                assert config_ids == {
                    link_type: f"cfg-{asset.delivery_drama_id}-{link_type}"
                    for link_type in links
                }

                product_id = service.create_product(
                    "album-1", {"drama_name": "剧A", "album_id": "album-1"}
                )
                assert product_id == "prod-album-1"

                spec = PlanSpec(
                    drama_name="剧A",
                    platform="TOMATO",
                    task_name="番茄#端免剧A20260806-test",
                    link_set=dict(links),
                    account_cids=list(cids),
                    product_id=product_id,
                    rule_version="v1",
                )
                external_task_id = service.submit_plan(spec)
                assert external_task_id.startswith("task-")

                status = service.poll_until_completed(
                    external_task_id, max_polls=3, interval_seconds=0
                )
                assert status == "COMPLETED"

                assert spec.link_set == links
                assert spec.account_cids == cids
                assert spec.product_id == product_id
            finally:
                engine.dispose()

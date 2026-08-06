"""平台 Adapter Mock 实现测试."""
from __future__ import annotations

from datetime import date, datetime, timezone

from backend.domain.ports.adapters import (
    DeliverySystemAdapter,
    DramaAsset,
    FeishuAdapter,
    OceanEngineAdapter,
    PromotionLink,
    TemplateInfo,
    TomatoAdapter,
)
from backend.domain.tasks.drama_task import DramaTask
from backend.platforms.mock.mock_delivery_system import MockDeliverySystemAdapter
from backend.platforms.mock.mock_feishu import MockFeishuAdapter
from backend.platforms.mock.mock_ocean_engine import MockOceanEngineAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter


class TestMockFeishuAdapter:
    """飞书 Mock 行为验证."""

    def test_fetch_tasks_returns_sample_tasks(self):
        adapter = MockFeishuAdapter()
        tasks = adapter.fetch_tasks(date(2026, 8, 6))
        assert tasks
        assert all(isinstance(task, DramaTask) for task in tasks)
        assert all(task.available_time.date() == date(2026, 8, 6) for task in tasks)

    def test_fetch_tasks_deterministic(self):
        adapter = MockFeishuAdapter()
        first = adapter.fetch_tasks(date(2026, 8, 6))
        second = adapter.fetch_tasks(date(2026, 8, 6))
        assert [task.id for task in first] == [task.id for task in second]

    def test_fetch_tasks_filters_injected_by_day(self):
        day = date(2026, 8, 6)
        injected = [
            DramaTask(
                drama_name="剧A",
                platform="TOMATO",
                available_time=datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
            ),
            DramaTask(
                drama_name="剧B",
                platform="TOMATO",
                available_time=datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc),
            ),
        ]
        adapter = MockFeishuAdapter(tasks=injected)
        assert [task.drama_name for task in adapter.fetch_tasks(day)] == ["剧A"]

    def test_write_completion_toggles_status(self):
        adapter = MockFeishuAdapter()
        assert adapter.read_status("task-1") == "PENDING"
        adapter.write_completion("task-1")
        assert adapter.read_status("task-1") == "OK"

    def test_write_links_recorded(self):
        adapter = MockFeishuAdapter()
        adapter.write_links("task-1", {"IAA": "mock://iaa/剧A?ep=1"})
        assert adapter.written_links == {"task-1": {"IAA": "mock://iaa/剧A?ep=1"}}


class TestMockTomatoAdapter:
    """番茄 Mock 行为验证."""

    def test_extract_iaa_link(self):
        adapter = MockTomatoAdapter()
        link = adapter.extract_iaa_link("剧A", 40, 1)
        assert isinstance(link, PromotionLink)
        assert link.promotion_url == "mock://iaa/剧A?ep=1"
        assert link.link_type == "IAA"
        assert link.url_length == len(link.promotion_url)

    def test_extract_iaa_link_deterministic(self):
        adapter = MockTomatoAdapter()
        first = adapter.extract_iaa_link("剧A", 40, 1)
        second = adapter.extract_iaa_link("剧A", 40, 1)
        assert first.promotion_url == second.promotion_url

    def test_scan_iap_templates_ranges(self):
        adapter = MockTomatoAdapter()
        templates = adapter.scan_iap_templates("剧A")
        assert len(templates) == 3
        assert all(isinstance(template, TemplateInfo) for template in templates)
        prices = [template.price for template in templates]
        assert any(2.6 <= price <= 5.0 for price in prices)
        assert any(8.8 <= price <= 13.8 for price in prices)
        assert any(price < 2.6 or price > 13.8 for price in prices)

    def test_scan_iap_templates_deterministic(self):
        adapter = MockTomatoAdapter()
        first = adapter.scan_iap_templates("剧A")
        second = adapter.scan_iap_templates("剧A")
        assert [t.template_id for t in first] == [t.template_id for t in second]

    def test_generate_iap_link(self):
        adapter = MockTomatoAdapter()
        template = TemplateInfo(
            template_id="tpl-剧A-2-9",
            drama_name="剧A",
            title="2.9 档模板",
            price=2.9,
            page_order=1,
        )
        link = adapter.generate_iap_link("剧A", template)
        assert link.promotion_url == "mock://iap/IAP/剧A?tpl=tpl-剧A-2-9"
        assert link.link_type == "IAP"


class TestMockDeliverySystemAdapter:
    """投放系统 Mock 行为验证."""

    def test_find_or_create_drama_asset_idempotent(self):
        adapter = MockDeliverySystemAdapter()
        first = adapter.find_or_create_drama_asset("剧A", "mock://iaa/剧A?ep=1")
        second = adapter.find_or_create_drama_asset("剧A", "mock://iaa/剧A?ep=1")
        assert isinstance(first, DramaAsset)
        assert first == second
        assert first.delivery_drama_id == second.delivery_drama_id

    def test_find_or_create_distinct_link_new_asset(self):
        adapter = MockDeliverySystemAdapter()
        first = adapter.find_or_create_drama_asset("剧A", "link-1")
        second = adapter.find_or_create_drama_asset("剧A", "link-2")
        assert first.delivery_drama_id != second.delivery_drama_id

    def test_ensure_promotion_config(self):
        adapter = MockDeliverySystemAdapter()
        assert (
            adapter.ensure_promotion_config(
                "dd-1", "IAA", "mock://iaa/剧A?ep=1", "剧A", "TOMATO"
            )
            == "IAA-TOMATO-剧A"
        )

    def test_submit_plan_deterministic(self):
        adapter = MockDeliverySystemAdapter()
        spec = {"drama_name": "剧A", "link_type": "IAA"}
        first = adapter.submit_plan(spec)
        second = adapter.submit_plan(spec)
        assert first == second
        assert first.startswith("task-")

    def test_poll_task_status_transitions(self):
        adapter = MockDeliverySystemAdapter()
        task_id = adapter.submit_plan({"drama_name": "剧A"})
        assert adapter.poll_task_status(task_id) == "SUBMITTED"
        assert adapter.poll_task_status(task_id) == "COMPLETED"

    def test_poll_task_status_injectable_rounds(self):
        adapter = MockDeliverySystemAdapter(poll_rounds_before_completed=2)
        task_id = adapter.submit_plan({"drama_name": "剧A"})
        assert adapter.poll_task_status(task_id) == "SUBMITTED"
        assert adapter.poll_task_status(task_id) == "SUBMITTED"
        assert adapter.poll_task_status(task_id) == "COMPLETED"


class TestMockOceanEngineAdapter:
    """巨量产品库 Mock 行为验证."""

    def test_create_product(self):
        adapter = MockOceanEngineAdapter()
        assert adapter.create_product("album-1", {"name": "剧A"}) == "prod-album-1"

    def test_verify_product(self):
        adapter = MockOceanEngineAdapter()
        assert adapter.verify_product("prod-album-1") is True


class TestAdapterProtocols:
    """Mock 实现满足 Domain Protocol."""

    def test_mocks_satisfy_protocols(self):
        assert isinstance(MockFeishuAdapter(), FeishuAdapter)
        assert isinstance(MockTomatoAdapter(), TomatoAdapter)
        assert isinstance(MockDeliverySystemAdapter(), DeliverySystemAdapter)
        assert isinstance(MockOceanEngineAdapter(), OceanEngineAdapter)

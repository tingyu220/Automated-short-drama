"""链接就绪服务的真实 Adapter 边界集成测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.application.services.link_readiness_service import LinkReadinessService
from backend.domain.ports.adapters import DramaAsset
from backend.domain.tasks.drama_task import DramaTask


class Preparation:
    def prepare_task(self, task, *, dry_run, now):
        task.link_status = "VALIDATED"
        task.link_set = {"IAA": "aweme://iaa"}
        return type("Outcome", (), {"status": "READY", "failure_code": None, "details": {}})()


class Delivery:
    def __init__(self):
        self.asset_calls = 0
        self.config_calls = 0

    def ensure_drama_asset(self, drama_name, link):
        self.asset_calls += 1
        return DramaAsset("dd-1", drama_name, link)

    def ensure_promotion_config(self, asset, link_type, link, platform):
        self.config_calls += 1
        return "iaa-番茄-剧A"


class Repo:
    def update(self, task):
        return task


class Workflow:
    def start_step(self, task_id, step_name):
        return type("Step", (), {})()

    def finish_step(self, step, result=None):
        return step

    def fail_step(self, step, error_code, error_message):
        return step


def test_link_ready_flow_is_idempotent_after_first_run() -> None:
    task = DramaTask(
        id="task-1",
        drama_name="剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 16, 8, tzinfo=timezone.utc),
    )
    delivery = Delivery()
    service = LinkReadinessService(Preparation(), delivery, Repo(), Workflow())

    service.execute(task, "LINK_READY", dry_run=False, now=task.available_time)
    service.execute(task, "LINK_READY", dry_run=False, now=task.available_time)

    assert delivery.asset_calls == 1
    assert delivery.config_calls == 1

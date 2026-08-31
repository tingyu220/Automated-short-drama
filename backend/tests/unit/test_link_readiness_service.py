"""链接就绪阶段编排测试。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.application.services.link_readiness_service import (
    LinkReadinessService,
)
from backend.application.services.plan_rules import build_promotion_config_name
from backend.domain.ports.adapters import DramaAsset
from backend.domain.tasks.drama_task import DramaTask


NOW = datetime(2026, 8, 16, 8, tzinfo=timezone.utc)


class MemoryTaskRepo:
    def __init__(self, task: DramaTask):
        self.task = task

    def get(self, task_id: str):
        return self.task if task_id == self.task.id else None

    def update(self, task: DramaTask):
        self.task = task
        return task


class FakePreparation:
    def __init__(self, task: DramaTask):
        self.task = task
        self.calls = 0

    def prepare_task(self, task, *, dry_run: bool, now):
        self.calls += 1
        task.link_set = {"IAA": "aweme://iaa", "9.9": "aweme://iap-99"}
        task.link_status = "VALIDATED"
        return type("Outcome", (), {"status": "READY", "failure_code": None, "details": {}})()


class IapWarningPreparation(FakePreparation):
    def prepare_task(self, task, *, dry_run: bool, now):
        result = super().prepare_task(task, dry_run=dry_run, now=now)
        result.details = {
            "iap_failures": [
                {
                    "link_type": "9.9",
                    "code": "TimeoutError",
                    "message": "9.9 模板生成超时",
                }
            ]
        }
        return result


class PersistingPreparation:
    """模拟准备服务保存了新任务实例，但没有修改 Worker 持有的旧实例。"""

    def __init__(self, repo: MemoryTaskRepo):
        self.repo = repo

    def prepare_task(self, task, *, dry_run: bool, now):
        persisted = DramaTask(
            id=task.id,
            drama_name=task.drama_name,
            platform=task.platform,
            available_time=task.available_time,
            status="READY",
            link_status="VALIDATED",
            link_set={"IAA": "aweme://persisted-iaa"},
        )
        self.repo.update(persisted)
        return type("Outcome", (), {"status": "READY", "failure_code": None, "details": {}})()


class FakeDeliveryFlow:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def ensure_drama_asset(self, drama_name: str, link: str) -> DramaAsset:
        self.calls.append(("find_or_create_drama_asset", (drama_name, link)))
        return DramaAsset("dd-1", drama_name, link)

    def ensure_promotion_config(self, asset, link_type, link, platform):
        self.calls.append(("ensure_promotion_config", (link_type, link)))
        return build_promotion_config_name(link_type, platform, "剧A")


class FakeWorkflowRepo:
    def __init__(self):
        self.steps: list[tuple[str, str, dict]] = []

    def start_step(self, task_id, step_name):
        step = type("Step", (), {"task_id": task_id, "step_name": step_name})()
        self.steps.append((task_id, step_name, {}))
        return step

    def finish_step(self, step, result=None):
        self.steps[-1] = (step.task_id, step.step_name, result or {})
        return step

    def fail_step(self, step, error_code, error_message):
        self.steps[-1] = (step.task_id, step.step_name, {"error_code": error_code})
        return step


def _task() -> DramaTask:
    return DramaTask(
        id="task-1",
        drama_name="剧A",
        platform="TOMATO",
        available_time=NOW,
    )


def test_link_extraction_target_stops_before_delivery() -> None:
    """仅提取链接不能访问投放系统。"""
    task = _task()
    delivery = FakeDeliveryFlow()
    service = LinkReadinessService(
        FakePreparation(task), delivery, MemoryTaskRepo(task), FakeWorkflowRepo()
    )

    result = service.execute(task, "LINK_EXTRACTION", dry_run=False, now=NOW)

    assert result.status == "LINK_EXTRACTED"
    assert delivery.calls == []
    assert task.current_stage == "LINK_EXTRACTION"


def test_link_ready_orders_asset_before_promotion_configs() -> None:
    """搭建链接必须先有投放系统剧目资源。"""
    task = _task()
    delivery = FakeDeliveryFlow()
    service = LinkReadinessService(
        FakePreparation(task), delivery, MemoryTaskRepo(task), FakeWorkflowRepo()
    )

    result = service.execute(task, "LINK_READY", dry_run=False, now=NOW)

    assert result.status == "LINK_READY"
    assert [call[0] for call in delivery.calls] == [
        "find_or_create_drama_asset",
        "ensure_promotion_config",
        "ensure_promotion_config",
    ]
    assert task.delivery_drama_id == "dd-1"
    assert task.promotion_configs == {
        "IAA": "iaa-番茄-剧A",
        "9.9": "9.9-番茄-剧A",
    }


def test_resume_skips_completed_link_stage() -> None:
    """已有冻结链接时恢复不得再次访问番茄。"""
    task = _task()
    task.link_status = "VALIDATED"
    task.link_set = {"IAA": "aweme://iaa"}
    preparation = FakePreparation(task)
    delivery = FakeDeliveryFlow()
    service = LinkReadinessService(
        preparation, delivery, MemoryTaskRepo(task), FakeWorkflowRepo()
    )

    service.execute(task, "LINK_READY", dry_run=False, now=NOW)

    assert preparation.calls == 0


def test_link_ready_reloads_links_saved_by_preparation() -> None:
    """提链保存新实例后，后续建剧目必须使用已冻结链接。"""
    task = _task()
    repo = MemoryTaskRepo(task)
    delivery = FakeDeliveryFlow()
    service = LinkReadinessService(
        PersistingPreparation(repo), delivery, repo, FakeWorkflowRepo()
    )

    result = service.execute(task, "LINK_READY", dry_run=False, now=NOW)

    assert result.status == "LINK_READY"
    assert delivery.calls[0] == (
        "find_or_create_drama_asset",
        ("剧A", "aweme://persisted-iaa"),
    )


def test_link_ready_keeps_iap_failure_in_stage_result() -> None:
    """IAP 失败须随 LINK_EXTRACTION 阶段记录，但 IAA 可继续搭建。"""
    task = _task()
    workflow = FakeWorkflowRepo()
    service = LinkReadinessService(
        IapWarningPreparation(task), FakeDeliveryFlow(), MemoryTaskRepo(task), workflow
    )

    result = service.execute(task, "LINK_READY", dry_run=False, now=NOW)

    assert result.status == "LINK_READY"
    assert result.details["iap_failures"][0]["link_type"] == "9.9"
    assert workflow.steps[0][2]["iap_failures"][0]["code"] == "TimeoutError"

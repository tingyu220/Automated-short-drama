"""端类型产线分离单元测试."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.tasks.drama_task import DramaTask
from backend.domain.tasks.end_type import EndType
from backend.domain.tasks.source_key import build_task_source_key
from backend.platforms.mock.mock_youxuan import MockYouxuanAdapter
from backend.platforms.mock.mock_tomato import MockTomatoAdapter
from backend.application.services.task_preparation_service import (
    TaskPreparationService,
)


class TestEndType:
    """EndType 常量与校验."""

    def test_constants(self):
        assert EndType.NATIVE == "NATIVE"
        assert EndType.MINIPROGRAM == "MINIPROGRAM"

    def test_all_set(self):
        assert EndType.ALL == frozenset({"NATIVE", "MINIPROGRAM"})

    def test_validate_native(self):
        assert EndType.validate("NATIVE") == "NATIVE"

    def test_validate_miniprogram(self):
        assert EndType.validate("MINIPROGRAM") == "MINIPROGRAM"

    def test_validate_invalid_raises(self):
        with pytest.raises(ValueError, match="不支持的端类型"):
            EndType.validate("UNKNOWN")


class TestDramaTaskEndType:
    """DramaTask end_type 默认值与赋值."""

    def test_default_is_native(self):
        task = DramaTask(
            drama_name="测试剧", platform="TOMATO",
            available_time=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        assert task.end_type == EndType.NATIVE

    def test_can_set_miniprogram(self):
        task = DramaTask(
            drama_name="测试剧", platform="TOMATO",
            available_time=datetime(2026, 8, 29, tzinfo=timezone.utc),
            end_type=EndType.MINIPROGRAM,
        )
        assert task.end_type == EndType.MINIPROGRAM


class TestSourceKeyWithEndType:
    """source_key 纳入 end_type 后，不同端类型产生不同 key."""

    def test_different_end_type_different_key(self):
        native_key = build_task_source_key("剧A", "TOMATO", "2026/08/29 10:00")
        mp_key = build_task_source_key(
            "剧A", "TOMATO", "2026/08/29 10:00", end_type=EndType.MINIPROGRAM
        )
        assert native_key != mp_key

    def test_same_end_type_same_key(self):
        k1 = build_task_source_key("剧A", "TOMATO", "2026/08/29 10:00")
        k2 = build_task_source_key("剧A", "TOMATO", "2026/08/29 10:00")
        assert k1 == k2

    def test_default_end_type_is_native(self):
        k1 = build_task_source_key("剧A", "TOMATO", "2026/08/29 10:00")
        k2 = build_task_source_key(
            "剧A", "TOMATO", "2026/08/29 10:00", end_type=EndType.NATIVE
        )
        assert k1 == k2


class TestMockYouxuanAdapter:
    """MockYouxuanAdapter 返回确定性链接."""

    def test_returns_promotion_link(self):
        adapter = MockYouxuanAdapter()
        links = adapter.extract_links("测试剧")
        assert len(links) == 1
        assert links[0].drama_name == "测试剧"
        assert links[0].source_platform == "YOUXUAN"
        assert links[0].source_entry == "MINIPROGRAM"
        assert links[0].link_status == "OK"
        assert links[0].promotion_url.startswith("mock://youxuan/")

    def test_different_drama_different_url(self):
        adapter = MockYouxuanAdapter()
        l1 = adapter.extract_links("剧A")
        l2 = adapter.extract_links("剧B")
        assert l1[0].promotion_url != l2[0].promotion_url


class MemoryTaskRepo:
    def __init__(self):
        self.items: dict[str, DramaTask] = {}

    def add(self, task):
        self.items[task.id] = task
        return task

    def get(self, task_id):
        return self.items.get(task_id)

    def update(self, task):
        self.items[task.id] = task
        return task


class MemoryQueueRepo:
    def __init__(self):
        self.items: dict[str, object] = {}

    def add(self, item):
        self.items[item.id] = item
        return item

    def list_by_task(self, task_id):
        return [i for i in self.items.values() if i.task_id == task_id]


class RecordingFeishu:
    def __init__(self, tasks):
        self.tasks = tasks
        self.writes: list[tuple[str, dict[str, str]]] = []

    def fetch_tasks(self, day):
        return list(self.tasks)

    def write_links(self, task_id, links):
        self.writes.append((task_id, dict(links)))


def _miniprogram_task(task_id="mp-1"):
    return DramaTask(
        id=task_id,
        sheet_row=int(task_id.split("-")[-1]),
        drama_name="小程序剧A",
        platform="TOMATO",
        available_time=datetime(2026, 8, 29, 10, tzinfo=timezone.utc),
        end_type=EndType.MINIPROGRAM,
    )


class TestTaskPreparationMiniprogram:
    """TaskPreparationService 对 MINIPROGRAM 产线分流."""

    def test_miniprogram_uses_youxuan_adapter(self):
        feishu = RecordingFeishu([_miniprogram_task()])
        tasks = MemoryTaskRepo()
        queue = MemoryQueueRepo()
        service = TaskPreparationService(
            feishu,
            MockTomatoAdapter(),
            tasks,
            queue,
            price_rules=[],
            youxuan=MockYouxuanAdapter(),
        )
        result = service.prepare_task(
            _miniprogram_task(),
            dry_run=True,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        assert result.status == "READY"
        task = tasks.get("mp-1")
        assert task is not None
        assert task.link_set
        assert "IAA" in task.link_set

    def test_miniprogram_without_youxuan_returns_no_links(self):
        feishu = RecordingFeishu([_miniprogram_task()])
        tasks = MemoryTaskRepo()
        queue = MemoryQueueRepo()
        service = TaskPreparationService(
            feishu,
            MockTomatoAdapter(),
            tasks,
            queue,
            price_rules=[],
        )
        result = service.prepare_task(
            _miniprogram_task(),
            dry_run=True,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        assert result.status == "MANUAL_REVIEW"
        assert result.failure_code == "NO_LINKS"

    def test_native_still_uses_tomato(self):
        native_task = DramaTask(
            id="nat-1",
            sheet_row=1,
            drama_name="端原生剧A",
            platform="TOMATO",
            available_time=datetime(2026, 8, 29, 10, tzinfo=timezone.utc),
            end_type=EndType.NATIVE,
        )
        feishu = RecordingFeishu([native_task])
        tasks = MemoryTaskRepo()
        queue = MemoryQueueRepo()
        service = TaskPreparationService(
            feishu,
            MockTomatoAdapter(),
            tasks,
            queue,
            price_rules=[],
        )
        result = service.prepare_task(
            native_task,
            dry_run=True,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        assert result.status == "READY"
        task = tasks.get("nat-1")
        assert task is not None
        assert "IAA" in task.link_set


class TestLinkReadinessMiniprogramSkip:
    """LinkReadinessService 对 MINIPROGRAM 跳过投放系统."""

    def _make_services(self):
        from backend.application.services.link_readiness_service import (
            LinkReadinessService,
        )
        from backend.application.services.task_preparation_service import (
            TaskPreparationService,
        )

        class StubWorkflowRepo:
            def start_step(self, task_id, step_name):
                return f"step-{task_id}-{step_name}"

            def finish_step(self, step, result):
                pass

            def fail_step(self, step, code, message):
                pass

            def list_steps_by_task(self, task_id):
                return []

        task = _miniprogram_task()
        feishu = RecordingFeishu([task])
        task_repo = MemoryTaskRepo()
        queue_repo = MemoryQueueRepo()
        preparation = TaskPreparationService(
            feishu,
            MockTomatoAdapter(),
            task_repo,
            queue_repo,
            price_rules=[],
            youxuan=MockYouxuanAdapter(),
        )

        class StubDelivery:
            def ensure_drama_asset(self, *a, **kw):
                raise AssertionError("MINIPROGRAM 不应调用投放系统")

            def ensure_promotion_config(self, *a, **kw):
                raise AssertionError("MINIPROGRAM 不应调用推广配置")

        readiness = LinkReadinessService(
            preparation,
            StubDelivery(),
            task_repo,
            StubWorkflowRepo(),
        )
        return readiness, task, task_repo

    def test_miniprogram_skips_delivery(self):
        readiness, task, task_repo = self._make_services()
        outcome = readiness.execute(
            task,
            "LINK_READY",
            dry_run=True,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        assert outcome.status == "LINK_READY"
        assert task_repo.get(task.id) is not None

"""任务前置准备：链接冻结、飞书回填与入队。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.application.services.task_preparation_service import (
    MANUAL_REVIEW,
    READY,
    TaskPreparationService,
)
from backend.domain.errors.domain_error import DramaMismatchError
from backend.domain.plans.plan_spec import PlanSpec
from backend.domain.ports.adapters import PromotionLink
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.platforms.mock.mock_tomato import MockTomatoAdapter


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
        self.items: dict[str, QueueItem] = {}

    def add(self, item):
        self.items[item.id] = item
        return item

    def list_by_task(self, task_id):
        return [item for item in self.items.values() if item.task_id == task_id]


class RecordingFeishu:
    def __init__(self, tasks):
        self.tasks = tasks
        self.writes: list[tuple[str, dict[str, str]]] = []

    def fetch_tasks(self, day):
        return list(self.tasks)

    def write_links(self, task_id, links):
        self.writes.append((task_id, dict(links)))


def _task(task_id="2", platform="TOMATO", links=None):
    return DramaTask(
        id=task_id,
        sheet_row=int(task_id),
        drama_name="剧A",
        platform=platform,
        available_time=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
        source_links=links or {},
    )


def test_prepare_tomato_freezes_links_writes_back_and_enqueues():
    feishu = RecordingFeishu([_task()])
    tasks = MemoryTaskRepo()
    queue = MemoryQueueRepo()
    service = TaskPreparationService(
        feishu, MockTomatoAdapter(), tasks, queue, price_rules=[]
    )

    result = service.prepare(
        date(2026, 8, 8),
        now=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
    )

    assert result.ready == 1
    saved = tasks.items["2"]
    assert saved.status == READY
    assert saved.link_status == "VALIDATED"
    assert saved.link_set["IAA"].startswith("mock://iaa/")
    assert feishu.writes[0][0] == "2"
    assert len(queue.items) == 1
    assert next(iter(queue.items.values())).state == QueueState.WAITING_TIME


def test_prepare_tomato_uses_real_episode_count_for_iaa_selection():
    class EpisodeTomato(MockTomatoAdapter):
        def get_episode_count(self, drama_name, available_time):
            return 51

    feishu = RecordingFeishu([_task()])
    tasks = MemoryTaskRepo()
    service = TaskPreparationService(
        feishu, EpisodeTomato(), tasks, MemoryQueueRepo(), price_rules=[]
    )

    result = service.prepare_task(
        _task(),
        dry_run=False,
        now=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
    )

    assert result.status == READY
    assert tasks.items["2"].link_set["IAA"].endswith("ep=2")
    assert feishu.writes[0][1]["IAA"].endswith("ep=2")


def test_prepare_normalizes_naive_persisted_time_before_tomato_calls():
    """数据库无时区时间按 UTC 传给番茄，避免匹配入口拒绝任务。"""

    class RecordingTomato(MockTomatoAdapter):
        def __init__(self):
            self.seen: list[datetime] = []

        def get_episode_count(self, drama_name, available_time):
            self.seen.append(available_time)
            return super().get_episode_count(drama_name, available_time)

    source = _task()
    source.available_time = datetime(2026, 8, 8, 10)
    existing = _task()
    existing.available_time = datetime(2026, 8, 8, 10)
    tomato = RecordingTomato()
    tasks = MemoryTaskRepo()
    tasks.add(existing)
    result = TaskPreparationService(
        RecordingFeishu([source]),
        tomato,
        tasks,
        MemoryQueueRepo(),
        price_rules=[],
    ).prepare_task(
        source,
        dry_run=False,
        now=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
    )

    assert result.status == READY
    assert tomato.seen == [datetime(2026, 8, 8, 10, tzinfo=timezone.utc)]


def test_special_length_links_are_written_but_sent_to_manual_review():
    class SpecialLengthTomato(MockTomatoAdapter):
        def extract_iaa_link(self, *args, **kwargs):
            return PromotionLink(
                drama_name="剧A",
                link_type="IAA",
                promotion_url="x" * 500,
                link_status="SPECIAL_LENGTH",
            )

    feishu = RecordingFeishu([_task()])
    tasks = MemoryTaskRepo()
    queue = MemoryQueueRepo()

    result = TaskPreparationService(
        feishu, SpecialLengthTomato(), tasks, queue, price_rules=[]
    ).prepare_task(
        _task(),
        dry_run=False,
        now=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
    )

    assert result.status == MANUAL_REVIEW
    assert result.failure_code == "SPECIAL_LENGTH"
    assert tasks.items["2"].link_status == "SPECIAL_LENGTH"
    assert tasks.items["2"].link_set == {"IAA": "x" * 500}
    assert feishu.writes == [("2", {"IAA": "x" * 500})]
    assert queue.items == {}


def test_prepare_jubian_uses_existing_links_without_tomato_call():
    class ExplodingTomato:
        def extract_iaa_link(self, *args, **kwargs):
            raise AssertionError("剧变不应进入番茄")

    _url = "aweme://playlet?playlet_id=123&version=2&advertise_param=abc&hash_res=def"
    links = {"IAA": _url, "9.9": _url}
    feishu = RecordingFeishu([_task(platform="JUBIAN", links=links)])
    tasks = MemoryTaskRepo()
    queue = MemoryQueueRepo()

    result = TaskPreparationService(
        feishu, ExplodingTomato(), tasks, queue, price_rules=[]
    ).prepare(
        date(2026, 8, 8),
        now=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
    )

    assert result.ready == 1
    assert tasks.items["2"].link_set == links
    assert feishu.writes == []


def test_prepare_missing_iaa_goes_manual_review_and_does_not_enqueue():
    class EmptyTomato(MockTomatoAdapter):
        def extract_iaa_link(self, *args, **kwargs):
            return PromotionLink(
                drama_name="剧A",
                link_type="IAA",
                promotion_url="",
                link_status="NOT_AVAILABLE",
            )

    feishu = RecordingFeishu([_task()])
    tasks = MemoryTaskRepo()
    queue = MemoryQueueRepo()

    result = TaskPreparationService(
        feishu, EmptyTomato(), tasks, queue, price_rules=[]
    ).prepare(
        date(2026, 8, 8),
        now=datetime(2026, 8, 8, 10, tzinfo=timezone.utc),
    )

    assert result.manual_review == 1
    assert tasks.items["2"].status == MANUAL_REVIEW
    assert queue.items == {}


def test_prepare_iaa_success_with_iap_scan_failure_still_enqueues() -> None:
    """IAP 扫描失败仅记录，不能阻断 IAA 驱动的投放系统搭建。"""

    class IapFailingTomato(MockTomatoAdapter):
        def scan_iap_templates(self, drama_name, available_time):
            raise TimeoutError("IAP 模板列表超时")

    task = _task()
    tasks = MemoryTaskRepo()
    queue = MemoryQueueRepo()
    result = TaskPreparationService(
        RecordingFeishu([task]),
        IapFailingTomato(),
        tasks,
        queue,
        price_rules=[],
    ).prepare_task(task, dry_run=False, now=task.available_time)

    assert result.status == READY
    assert tasks.get(task.id).link_set["IAA"].startswith("mock://iaa/")
    assert len(queue.items) == 1
    assert result.details["iap_failures"] == [
        {
            "link_type": "IAP",
            "code": "TimeoutError",
            "message": "IAP 模板列表超时",
        }
    ]


def test_prepare_is_idempotent_for_validated_task():
    task = _task(links={"IAA": "aweme://frozen"})
    task.link_set = dict(task.source_links)
    task.link_status = "VALIDATED"
    feishu = RecordingFeishu([task])
    tasks = MemoryTaskRepo()
    tasks.add(task)
    queue = MemoryQueueRepo()
    service = TaskPreparationService(
        feishu, MockTomatoAdapter(), tasks, queue, price_rules=[]
    )

    now = datetime(2026, 8, 8, 10, tzinfo=timezone.utc)
    service.prepare(date(2026, 8, 8), now=now)
    service.prepare(date(2026, 8, 8), now=now)

    assert len(queue.items) == 1
    assert feishu.writes == []


def test_prepare_before_available_time_does_not_open_tomato() -> None:
    class ExplodingTomato:
        def extract_iaa_link(self, *args, **kwargs):
            raise AssertionError("E 时间前不应打开番茄")

    task = _task()
    feishu = RecordingFeishu([task])
    result = TaskPreparationService(
        feishu,
        ExplodingTomato(),
        MemoryTaskRepo(),
        MemoryQueueRepo(),
        price_rules=[],
    ).prepare(
        date(2026, 8, 8),
        now=task.available_time - timedelta(seconds=1),
    )

    assert result.prepared == 0
    assert result.skipped == 1
    assert feishu.writes == []


def test_prepare_dry_run_freezes_local_snapshot_without_feishu_write() -> None:
    task = _task()
    feishu = RecordingFeishu([task])
    tasks = MemoryTaskRepo()
    result = TaskPreparationService(
        feishu,
        MockTomatoAdapter(),
        tasks,
        MemoryQueueRepo(),
        price_rules=[],
    ).prepare(
        date(2026, 8, 8),
        dry_run=True,
        now=task.available_time,
    )

    assert result.ready == 1
    assert tasks.get(task.id).link_status == "VALIDATED"
    assert tasks.get(task.id).link_set["IAA"].startswith("mock://iaa/")
    assert feishu.writes == []


def test_drama_mismatch_is_saved_without_write_or_enqueue() -> None:
    """IAA 同名剧不确定时仍不得回填链接或进入后续队列。"""

    class MismatchTomato(MockTomatoAdapter):
        def extract_iaa_link(self, *args, **kwargs):
            raise DramaMismatchError(
                "详情时间不一致",
                details={
                    "stage": "DETAIL",
                    "expected_minute": "2026-08-08T18:00:00+08:00",
                    "match_count": 0,
                },
            )

    task = _task()
    feishu = RecordingFeishu([task])
    tasks = MemoryTaskRepo()
    queue = MemoryQueueRepo()
    service = TaskPreparationService(
        feishu,
        MismatchTomato(),
        tasks,
        queue,
        price_rules=[],
    )

    result = service.prepare_task(
        task,
        dry_run=False,
        now=task.available_time,
    )

    assert result.status == MANUAL_REVIEW
    assert result.failure_code == "DRAMA_MISMATCH"
    assert result.details["stage"] == "DETAIL"
    assert tasks.get(task.id).link_status == "DRAMA_MISMATCH"
    assert feishu.writes == []
    assert queue.items == {}

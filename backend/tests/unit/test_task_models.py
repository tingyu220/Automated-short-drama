"""任务队列领域模型与 ORM 单元测试."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from backend.domain.tasks.drama_task import DramaTask, TaskStatus
from backend.domain.queue.queue_item import QueueItem, QueueState
from backend.domain.workflow.step_run import StepRun, StepStatus
from backend.domain.workflow.workflow_run import WorkflowRun
from backend.domain.ledger.task_ledger import TaskLedger
from backend.domain.ports.repositories import (
    TaskRepository,
    QueueRepository,
    WorkflowRepository,
    LedgerRepository,
)
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.task import (
    DramaTaskRecord,
    QueueItemRecord,
    WorkflowRunRecord,
    StepRunRecord,
    TaskLedgerRecord,
)
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.engine import create_app_engine


# ── Domain dataclass 默认值与常量 ──────────────────────────────


class TestDramaTaskDefaults:
    """DramaTask dataclass 默认值."""

    def test_default_status_is_waiting_time(self):
        task = DramaTask(
            drama_name="测试剧", platform="TOMATO",
            available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
        assert task.status == TaskStatus.WAITING_TIME

    def test_default_id_is_empty_string(self):
        task = DramaTask(
            drama_name="测试剧", platform="TOMATO",
            available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
        assert task.id == ""

    def test_sheet_row_owner_default_none(self):
        task = DramaTask(
            drama_name="测试剧", platform="TOMATO",
            available_time=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )
        assert task.sheet_row is None
        assert task.owner is None


class TestQueueItemDefaults:
    """QueueItem dataclass 默认值."""

    def test_default_state_is_waiting_time(self):
        item = QueueItem(task_id="t1")
        assert item.state == QueueState.WAITING_TIME

    def test_default_priority_zero(self):
        item = QueueItem(task_id="t1")
        assert item.priority == 0

    def test_attempt_count_starts_zero(self):
        item = QueueItem(task_id="t1")
        assert item.attempt_count == 0

    def test_claimed_by_lease_until_default_none(self):
        item = QueueItem(task_id="t1")
        assert item.claimed_by is None
        assert item.lease_until is None
        assert item.next_run_at is None


class TestStepRunDefaults:
    """StepRun dataclass 默认值."""

    def test_default_status_pending(self):
        step = StepRun(workflow_run_id="wr1", step_name="submit")
        assert step.status == StepStatus.PENDING

    def test_error_fields_default_none(self):
        step = StepRun(workflow_run_id="wr1", step_name="submit")
        assert step.result_json is None
        assert step.error_code is None
        assert step.error_message is None


class TestStatusConstants:
    """状态常量验证."""

    def test_task_status_values(self):
        assert TaskStatus.WAITING_TIME == "WAITING_TIME"
        assert TaskStatus.READY == "READY"
        assert TaskStatus.RUNNING == "RUNNING"
        assert TaskStatus.COMPLETED == "COMPLETED"
        assert TaskStatus.MANUAL_REVIEW == "MANUAL_REVIEW"
        assert TaskStatus.FAILED == "FAILED"
        assert TaskStatus.CANCELLED == "CANCELLED"

    def test_queue_state_values(self):
        assert QueueState.WAITING_TIME == "WAITING_TIME"
        assert QueueState.QUEUED == "QUEUED"
        assert QueueState.CLAIMED == "CLAIMED"
        assert QueueState.RUNNING == "RUNNING"
        assert QueueState.COMPLETED == "COMPLETED"
        assert QueueState.CANCELLED == "CANCELLED"

    def test_step_status_values(self):
        assert StepStatus.PENDING == "PENDING"
        assert StepStatus.RUNNING == "RUNNING"
        assert StepStatus.COMPLETED == "COMPLETED"
        assert StepStatus.SKIPPED == "SKIPPED"
        assert StepStatus.FAILED == "FAILED"


# ── 迁移后五张表存在 ────────────────────────────────────────


class TestMigrationTables:
    """Alembic upgrade head 后五张表存在."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.db_url = f"sqlite:///{db_path}"
        run_migrations(self.db_url)
        self.engine = create_app_engine(self.db_url)
        yield
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _table_exists(self, table_name: str) -> bool:
        with self.engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            return row is not None

    def test_drama_task_table_exists(self):
        assert self._table_exists("drama_task")

    def test_queue_item_table_exists(self):
        assert self._table_exists("queue_item")

    def test_workflow_run_table_exists(self):
        assert self._table_exists("workflow_run")

    def test_step_run_table_exists(self):
        assert self._table_exists("step_run")

    def test_task_ledger_table_exists(self):
        assert self._table_exists("task_ledger")

    def test_all_tables_exist(self):
        for name in (
            "drama_task", "queue_item", "workflow_run",
            "step_run", "task_ledger",
        ):
            assert self._table_exists(name), f"{name} 表应存在"


# ── ORM 写入 / 读取 ────────────────────────────────────────


class TestOrmWriteRead:
    """ORM 写入 DramaTask 与 QueueItem 后能读回基本字段."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.db_url = f"sqlite:///{db_path}"

        # 手动建表（不走 Alembic）
        self.engine = create_engine(self.db_url, connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        yield
        self.session.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_write_read_drama_task(self):
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        record = DramaTaskRecord(
            id=task_id,
            drama_name="霸道总裁爱上我",
            platform="TOMATO",
            available_time=now,
            sheet_row=5,
            owner="worker-1",
            status="READY",
        )
        self.session.add(record)
        self.session.commit()

        fetched = self.session.get(DramaTaskRecord, task_id)
        assert fetched is not None
        assert fetched.drama_name == "霸道总裁爱上我"
        assert fetched.platform == "TOMATO"
        assert fetched.sheet_row == 5
        assert fetched.owner == "worker-1"
        assert fetched.status == "READY"

    def test_write_read_queue_item(self):
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        task_record = DramaTaskRecord(
            id=task_id,
            drama_name="测试剧",
            platform="TOMATO",
            available_time=now,
        )
        self.session.add(task_record)
        self.session.flush()

        item_id = str(uuid.uuid4())
        item = QueueItemRecord(
            id=item_id,
            task_id=task_id,
            state="QUEUED",
            priority=10,
            attempt_count=3,
        )
        self.session.add(item)
        self.session.commit()

        fetched = self.session.get(QueueItemRecord, item_id)
        assert fetched is not None
        assert fetched.task_id == task_id
        assert fetched.state == "QUEUED"
        assert fetched.priority == 10
        assert fetched.attempt_count == 3

    def test_queue_item_foreign_key_constraint(self):
        """queue_item.task_id 引用不存在的 drama_task 应失败."""
        item = QueueItemRecord(
            id=str(uuid.uuid4()),
            task_id="nonexistent-task",
            state="QUEUED",
        )
        self.session.add(item)
        with pytest.raises(Exception):
            self.session.commit()
        self.session.rollback()


# ── Repository Protocol 接口定义验证 ────────────────────────


class TestRepositoryProtocols:
    """验证 Repository Protocol 接口未依赖 SQLAlchemy."""

    def test_task_repository_is_protocol(self):
        assert hasattr(TaskRepository, "add")
        assert hasattr(TaskRepository, "get")
        assert hasattr(TaskRepository, "update")
        assert hasattr(TaskRepository, "list_by_state")

    def test_queue_repository_is_protocol(self):
        assert hasattr(QueueRepository, "add")
        assert hasattr(QueueRepository, "get")
        assert hasattr(QueueRepository, "update")
        assert hasattr(QueueRepository, "list_by_state")

    def test_workflow_repository_is_protocol(self):
        assert hasattr(WorkflowRepository, "add_workflow")
        assert hasattr(WorkflowRepository, "get_workflow")
        assert hasattr(WorkflowRepository, "add_step")
        assert hasattr(WorkflowRepository, "get_step")

    def test_ledger_repository_is_protocol(self):
        assert hasattr(LedgerRepository, "add")
        assert hasattr(LedgerRepository, "get")
        assert hasattr(LedgerRepository, "update")
        assert hasattr(LedgerRepository, "list_by_task")

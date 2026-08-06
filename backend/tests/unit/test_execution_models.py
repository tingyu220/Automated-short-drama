"""执行事件与产物领域模型及 ORM 测试."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.domain.execution.execution_artifact import (
    ArtifactType,
    ExecutionArtifact,
)
from backend.domain.execution.execution_event import EventLevel, ExecutionEvent
from backend.infrastructure.database.base import Base
from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.models.execution import (
    ExecutionArtifactRecord,
    ExecutionEventRecord,
)
from backend.infrastructure.database.models.task import (
    DramaTaskRecord,
    StepRunRecord,
    WorkflowRunRecord,
)


class TestExecutionEventDefaults:
    """ExecutionEvent dataclass 默认值."""

    def test_default_id_is_empty_string(self):
        event = ExecutionEvent(
            task_id="t1",
            event_type="TASK_STARTED",
            message="任务开始",
        )
        assert event.id == ""

    def test_default_level_is_info(self):
        event = ExecutionEvent(
            task_id="t1",
            event_type="TASK_STARTED",
            message="任务开始",
        )
        assert event.level == EventLevel.INFO

    def test_context_json_default_none(self):
        event = ExecutionEvent(
            task_id="t1",
            event_type="TASK_STARTED",
            message="任务开始",
        )
        assert event.context_json is None


class TestExecutionArtifactDefaults:
    """ExecutionArtifact dataclass 默认值."""

    def test_default_id_is_empty_string(self):
        artifact = ExecutionArtifact(
            task_id="t1",
            artifact_type=ArtifactType.LOG,
            path="/tmp/a.log",
            size_bytes=10,
        )
        assert artifact.id == ""

    def test_step_run_id_and_checksum_default_none(self):
        artifact = ExecutionArtifact(
            task_id="t1",
            artifact_type=ArtifactType.LOG,
            path="/tmp/a.log",
            size_bytes=10,
        )
        assert artifact.step_run_id is None
        assert artifact.checksum is None


class TestExecutionConstants:
    """执行事件与产物常量验证."""

    def test_event_level_values(self):
        assert EventLevel.INFO == "INFO"
        assert EventLevel.WARNING == "WARNING"
        assert EventLevel.ERROR == "ERROR"

    def test_artifact_type_values(self):
        assert ArtifactType.SCREENSHOT == "SCREENSHOT"
        assert ArtifactType.LOG == "LOG"
        assert ArtifactType.HTML == "HTML"
        assert ArtifactType.OTHER == "OTHER"


class TestMigrationTables:
    """Alembic upgrade head 后执行事件与产物表存在."""

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

    def test_execution_tables_exist(self):
        assert self._table_exists("execution_event")
        assert self._table_exists("execution_artifact")


class TestOrmWriteRead:
    """ORM 写入/读取 ExecutionEvent 与 ExecutionArtifact."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "test.db"
        self.db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(
            self.db_url, connect_args={"check_same_thread": False}
        )

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

    def test_write_read_execution_event(self):
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        task = DramaTaskRecord(
            id=task_id,
            drama_name="测试剧",
            platform="TOMATO",
            available_time=now,
        )
        self.session.add(task)
        self.session.flush()

        event_id = str(uuid.uuid4())
        record = ExecutionEventRecord(
            id=event_id,
            task_id=task_id,
            event_type="TASK_STARTED",
            level="INFO",
            message="任务开始",
            context_json='{"step": "submit"}',
            occurred_at=now,
        )
        self.session.add(record)
        self.session.commit()

        fetched = self.session.get(ExecutionEventRecord, event_id)
        assert fetched is not None
        assert fetched.task_id == task_id
        assert fetched.event_type == "TASK_STARTED"
        assert fetched.level == "INFO"
        assert fetched.message == "任务开始"
        assert fetched.context_json == '{"step": "submit"}'

    def test_write_read_execution_artifact(self):
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        task = DramaTaskRecord(
            id=task_id,
            drama_name="测试剧",
            platform="TOMATO",
            available_time=now,
        )
        workflow = WorkflowRunRecord(
            id=str(uuid.uuid4()),
            task_id=task_id,
            status="RUNNING",
        )
        self.session.add_all([task, workflow])
        self.session.flush()
        step_run = StepRunRecord(
            id=str(uuid.uuid4()),
            workflow_run_id=workflow.id,
            step_name="submit",
        )
        self.session.add(step_run)
        self.session.flush()

        artifact_id = str(uuid.uuid4())
        record = ExecutionArtifactRecord(
            id=artifact_id,
            task_id=task_id,
            step_run_id=step_run.id,
            artifact_type="LOG",
            path="/tmp/run.log",
            size_bytes=1024,
            checksum="abc123",
        )
        self.session.add(record)
        self.session.commit()

        fetched = self.session.get(ExecutionArtifactRecord, artifact_id)
        assert fetched is not None
        assert fetched.task_id == task_id
        assert fetched.step_run_id == step_run.id
        assert fetched.artifact_type == "LOG"
        assert fetched.path == "/tmp/run.log"
        assert fetched.size_bytes == 1024
        assert fetched.checksum == "abc123"

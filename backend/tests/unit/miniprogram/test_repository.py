"""MiniProgram 仓储测试 + 数据隔离验证。

验证：
1. MiniProgram 仓储可以正常 CRUD
2. MiniProgram 仓储不会读写 Native 表
3. album_id 可以正常读取（唯一允许共享的业务数据）
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from backend.infrastructure.database.base import Base
from backend.miniprogram.domain.task_data import MiniProgramTaskData
from backend.miniprogram.domain.workflow_state import MiniProgramWorkflowStatus
from backend.miniprogram.infrastructure.database.models.miniprogram_task import (
    MiniProgramTaskRecord,
)
from backend.miniprogram.infrastructure.database.repositories.miniprogram_repository import (
    SqlAlchemyMiniProgramTaskRepository,
)


# ── Fake Repository（内存实现） ────────────────────────────


class FakeMiniProgramTaskRepository:
    """内存版 MiniProgram 仓储，用于快速测试。"""

    def __init__(self) -> None:
        self._data: dict[str, MiniProgramTaskData] = {}

    def save(self, task_data: MiniProgramTaskData) -> MiniProgramTaskData:
        task_data.touch()
        self._data[task_data.task_id] = task_data
        return task_data

    def get_by_task_id(self, task_id: str) -> MiniProgramTaskData | None:
        return self._data.get(task_id)

    def list_all(self) -> list[MiniProgramTaskData]:
        return list(self._data.values())

    def update_status(
        self, task_id: str, status: str
    ) -> MiniProgramTaskData | None:
        data = self._data.get(task_id)
        if data is None:
            return None
        data.workflow_status = status
        data.touch()
        return data

    def delete(self, task_id: str) -> bool:
        if task_id not in self._data:
            return False
        del self._data[task_id]
        return True


# ── helpers ────────────────────────────────────────────────


def _sample_task(task_id: str = "t-001") -> MiniProgramTaskData:
    return MiniProgramTaskData(
        task_id=task_id,
        drama_name="悍妇儿媳掌全局",
        operator_name="田雨",
        operator_code="TY",
        organization_group="投放一组",
        organization_path="投放部/一组",
        album_id="alb-001",
    )


# ── Fake Repository 测试 ──────────────────────────────────


class TestFakeMiniProgramRepository:
    def test_save_and_get(self):
        repo = FakeMiniProgramTaskRepository()
        data = _sample_task()
        result = repo.save(data)
        assert result.task_id == "t-001"

        fetched = repo.get_by_task_id("t-001")
        assert fetched is not None
        assert fetched.drama_name == "悍妇儿媳掌全局"

    def test_get_missing_returns_none(self):
        repo = FakeMiniProgramTaskRepository()
        assert repo.get_by_task_id("nonexistent") is None

    def test_update_status(self):
        repo = FakeMiniProgramTaskRepository()
        repo.save(_sample_task())
        result = repo.update_status("t-001", MiniProgramWorkflowStatus.CONTEXT_READY)
        assert result is not None
        assert result.workflow_status == MiniProgramWorkflowStatus.CONTEXT_READY

    def test_delete(self):
        repo = FakeMiniProgramTaskRepository()
        repo.save(_sample_task())
        assert repo.delete("t-001") is True
        assert repo.get_by_task_id("t-001") is None

    def test_delete_missing_returns_false(self):
        repo = FakeMiniProgramTaskRepository()
        assert repo.delete("nonexistent") is False

    def test_list_all(self):
        repo = FakeMiniProgramTaskRepository()
        repo.save(_sample_task("t-001"))
        repo.save(_sample_task("t-002"))
        assert len(repo.list_all()) == 2

    def test_album_id_preserved(self):
        """album_id 是唯一允许跨域的字段，必须正确保存。"""
        repo = FakeMiniProgramTaskRepository()
        data = _sample_task()
        data.album_id = "alb-shared-123"
        repo.save(data)
        fetched = repo.get_by_task_id("t-001")
        assert fetched is not None
        assert fetched.album_id == "alb-shared-123"

    def test_no_native_fields(self):
        """MiniProgramTaskData 不应包含 Native 业务字段。"""
        data = _sample_task()
        assert not hasattr(data, "link_set")
        assert not hasattr(data, "promotion_assets")
        assert not hasattr(data, "native_status")
        assert not hasattr(data, "tomato_status")


# ── SQLAlchemy Repository 测试 ─────────────────────────────


class TestSqlAlchemyMiniProgramRepository:
    @pytest.fixture
    def session(self):
        engine = create_engine("sqlite:///:memory:")
        # 只创建 miniprogram_task 表，不创建 native 表
        MiniProgramTaskRecord.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
        engine.dispose()

    def test_save_and_get(self, session: Session):
        repo = SqlAlchemyMiniProgramTaskRepository(session)
        data = _sample_task()
        result = repo.save(data)
        assert result.task_id == "t-001"
        assert result.id  # 自动生成了 id

        fetched = repo.get_by_task_id("t-001")
        assert fetched is not None
        assert fetched.drama_name == "悍妇儿媳掌全局"
        assert fetched.operator_code == "TY"

    def test_update_existing(self, session: Session):
        repo = SqlAlchemyMiniProgramTaskRepository(session)
        repo.save(_sample_task())

        data = _sample_task()
        data.drama_name = "新剧名"
        result = repo.save(data)
        assert result.drama_name == "新剧名"

        fetched = repo.get_by_task_id("t-001")
        assert fetched is not None
        assert fetched.drama_name == "新剧名"

    def test_update_status(self, session: Session):
        repo = SqlAlchemyMiniProgramTaskRepository(session)
        repo.save(_sample_task())
        result = repo.update_status("t-001", MiniProgramWorkflowStatus.CONTEXT_READY)
        assert result is not None
        assert result.workflow_status == MiniProgramWorkflowStatus.CONTEXT_READY

    def test_delete(self, session: Session):
        repo = SqlAlchemyMiniProgramTaskRepository(session)
        repo.save(_sample_task())
        assert repo.delete("t-001") is True
        assert repo.get_by_task_id("t-001") is None

    def test_list_all(self, session: Session):
        repo = SqlAlchemyMiniProgramTaskRepository(session)
        repo.save(_sample_task("t-001"))
        repo.save(_sample_task("t-002"))
        items = repo.list_all()
        assert len(items) == 2

    def test_album_id_preserved(self, session: Session):
        repo = SqlAlchemyMiniProgramTaskRepository(session)
        data = _sample_task()
        data.album_id = "alb-shared-456"
        repo.save(data)
        fetched = repo.get_by_task_id("t-001")
        assert fetched is not None
        assert fetched.album_id == "alb-shared-456"


# ── 数据隔离测试 ───────────────────────────────────────────


class TestDataIsolation:
    """验证 MiniProgram 仓储与 Native 数据完全隔离。"""

    def test_miniprogram_table_only(self):
        """MiniProgram ORM 只定义了 miniprogram_task 表，
        不应包含 promotion_asset 等 Native 表。"""
        # 检查 MiniProgramTaskRecord 的表名
        assert MiniProgramTaskRecord.__tablename__ == "miniprogram_task"

    def test_no_native_table_access(self):
        """MiniProgram 仓储模块不应导入 Native 表模型。"""
        import inspect

        source = inspect.getsource(SqlAlchemyMiniProgramTaskRepository)
        assert "PromotionAsset" not in source
        assert "promotion_asset" not in source
        assert "Native" not in source

    def test_miniprogram_task_record_has_no_native_fields(self):
        """ORM 模型字段中不应包含 Native 业务字段。"""
        mapper = inspect(MiniProgramTaskRecord)
        column_names = {c.key for c in mapper.columns}

        # 不应有 Native 字段
        assert "source_platform" not in column_names
        assert "link_type" not in column_names
        assert "promotion_url" not in column_names
        assert "link_set_id" not in column_names

        # 应有 MiniProgram 自己的字段
        assert "task_id" in column_names
        assert "drama_name" in column_names
        assert "operator_code" in column_names
        assert "workflow_status" in column_names
        # album_id 是唯一允许共享的
        assert "album_id" in column_names

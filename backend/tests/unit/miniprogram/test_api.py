"""M0-7 API Contract 单元测试。

覆盖四个 GET 端点：
- GET /api/miniprogram/tasks
- GET /api/miniprogram/tasks/{task_id}
- GET /api/miniprogram/config
- GET /api/miniprogram/discovery/{task_id}
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.base import Base
from backend.miniprogram.infrastructure.database.models.miniprogram_task import (
    MiniProgramTaskRecord,
)
from backend.interfaces.api.main import create_app
from backend.miniprogram.platforms.youxuan.network.discovery_storage import (
    save_captures_to_artifacts,
)
from backend.miniprogram.platforms.youxuan.network.network_listener import (
    NetworkCaptureRecord,
)


# ── fixtures ───────────────────────────────────────────────


@pytest.fixture
def temp_db(tmp_path: Path):
    """创建临时 SQLite 数据库，只含 miniprogram_task 表。"""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    MiniProgramTaskRecord.__table__.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def app_client(temp_db):
    """创建 TestClient，使用临时 DB。"""
    # 替换 get_session 返回测试 session
    import backend.interfaces.api.routes.miniprogram as mp_routes

    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app = create_app(dist_dir=None)
    app.dependency_overrides[mp_routes.get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _insert_task(db, task_id: str = "mp-001", **overrides):
    """插入一条测试任务。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    record = MiniProgramTaskRecord(
        id=f"id-{task_id}",
        task_id=task_id,
        drama_name=overrides.get("drama_name", "悍妇儿媳掌全局"),
        operator_name=overrides.get("operator_name", "田雨"),
        operator_code=overrides.get("operator_code", "TY"),
        organization_group=overrides.get("organization_group", "投放一组"),
        organization_path=overrides.get("organization_path", "投放部/一组"),
        drama_short_name=overrides.get("drama_short_name", None),
        album_id=overrides.get("album_id", "alb-001"),
        workflow_status=overrides.get("workflow_status", "NOT_STARTED"),
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


# ── GET /api/miniprogram/tasks ────────────────────────────


class TestListTasks:
    def test_empty_list(self, app_client):
        resp = app_client.get("/api/miniprogram/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, app_client, temp_db):
        _insert_task(temp_db, "mp-001")
        _insert_task(temp_db, "mp-002", drama_name="另一部剧")
        temp_db.commit()

        resp = app_client.get("/api/miniprogram/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        task_ids = {t["task_id"] for t in data}
        assert "mp-001" in task_ids
        assert "mp-002" in task_ids

    def test_task_fields(self, app_client, temp_db):
        _insert_task(temp_db, "mp-001", album_id="alb-test")
        temp_db.commit()

        resp = app_client.get("/api/miniprogram/tasks")
        task = resp.json()[0]
        assert task["task_id"] == "mp-001"
        assert task["drama_name"] == "悍妇儿媳掌全局"
        assert task["operator_code"] == "TY"
        assert task["album_id"] == "alb-test"
        assert task["workflow_status"] == "NOT_STARTED"


# ── GET /api/miniprogram/tasks/{task_id} ──────────────────


class TestGetTask:
    def test_found(self, app_client, temp_db):
        _insert_task(temp_db, "mp-001")
        temp_db.commit()

        resp = app_client.get("/api/miniprogram/tasks/mp-001")
        assert resp.status_code == 200
        task = resp.json()
        assert task["task_id"] == "mp-001"
        assert task["drama_name"] == "悍妇儿媳掌全局"

    def test_not_found(self, app_client):
        resp = app_client.get("/api/miniprogram/tasks/nonexistent")
        assert resp.status_code == 404


# ── GET /api/miniprogram/config ───────────────────────────


class TestListConfigs:
    def test_returns_lezhen(self, app_client):
        resp = app_client.get("/api/miniprogram/config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        lezhen = next(c for c in data if c["config_name"] == "lezhen")
        assert lezhen["mini_program"]["app_id"] == "wx10501bcb2a609cd1"
        assert lezhen["mini_program"]["name"] == "乐珍剧场"
        assert lezhen["promotion"]["charge_type"] == "每集固定价格"
        assert "2.9" in lezhen["price_tiers"]
        assert "9.9" in lezhen["price_tiers"]


# ── GET /api/miniprogram/discovery/{task_id} ─────────────


class TestGetDiscovery:
    def test_found(self, app_client, tmp_path: Path):
        # 保存测试数据
        captures = [
            NetworkCaptureRecord(
                url="https://api.youxuan.cn/promotion/list",
                method="GET",
                status=200,
                endpoint_type="PROMOTION_LIST",
                response_body={"code": 0, "data": [{"id": "p1"}]},
                captured_at="2024-01-01T00:00:00+00:00",
            ),
        ]
        saved_dir = save_captures_to_artifacts(
            captures, "mp-001", artifacts_root=tmp_path
        )
        assert saved_dir.exists()

        # 临时替换默认 artifacts 目录
        import backend.interfaces.api.routes.miniprogram as mp_routes
        from backend.miniprogram.platforms.youxuan.network import discovery_storage

        original_load = mp_routes.load_captures_from_artifacts

        def mock_load(task_id, artifacts_root=None):
            return original_load(task_id, artifacts_root=tmp_path)

        mp_routes.load_captures_from_artifacts = mock_load
        try:
            resp = app_client.get("/api/miniprogram/discovery/mp-001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["task_id"] == "mp-001"
            assert data["capture_count"] == 1
            assert "PROMOTION_LIST" in data["endpoint_types"]
            assert len(data["captures"]) == 1
            assert data["captures"][0]["endpoint_type"] == "PROMOTION_LIST"
        finally:
            mp_routes.load_captures_from_artifacts = original_load

    def test_not_found(self, app_client):
        resp = app_client.get("/api/miniprogram/discovery/nonexistent")
        assert resp.status_code == 404


# ── M0 限制验证 ───────────────────────────────────────────


class TestM0NoWriteEndpoints:
    """M0 不允许创建/修改/删除。"""

    def test_no_post_tasks(self, app_client):
        resp = app_client.post("/api/miniprogram/tasks", json={})
        assert resp.status_code == 405

    def test_no_post_config(self, app_client):
        resp = app_client.post("/api/miniprogram/config", json={})
        assert resp.status_code == 405

    def test_no_post_discovery(self, app_client):
        resp = app_client.post("/api/miniprogram/discovery/mp-001", json={})
        assert resp.status_code == 405

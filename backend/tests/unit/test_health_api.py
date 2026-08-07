"""健康检查 API 测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models.worker import WorkerLeaseRecord
from backend.interfaces.api.main import create_app


@pytest.fixture
def client():
    """创建测试客户端。"""
    app = create_app()
    return TestClient(app)


class TestHealthz:
    """GET /healthz 测试。"""

    def test_returns_200_and_ok(self, client):
        """健康检查返回 200 且 status=ok。"""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_allow_final_submit_default_false(self, client):
        """默认 allow_final_submit 为 false。"""
        response = client.get("/healthz")
        assert response.json()["allow_final_submit"] is False

    def test_response_contains_expected_fields(self, client):
        """响应包含 app_name/version/database/config 字段。"""
        data = client.get("/healthz").json()
        assert "app_name" in data
        assert data["app_name"] == "short-drama-delivery-workbuddy"
        assert "version" in data
        assert data["version"] == "0.1.0"
        assert "database" in data
        assert "config" in data
        assert data["config"] == "ok"

    def test_unregistered_route_returns_404(self, client):
        """未注册路由返回 404。"""
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_allow_final_submit_true_via_env(self, monkeypatch):
        """设置 WORKBUDDY_ALLOW_FINAL_SUBMIT=true 后响应为 true。"""
        monkeypatch.setenv("WORKBUDDY_ALLOW_FINAL_SUBMIT", "true")
        app = create_app()
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.json()["allow_final_submit"] is True

    def test_database_unavailable_returns_degraded(self, monkeypatch):
        """数据库不可用时返回 200、status=degraded、database=error。"""
        def _raise(*args, **kwargs):
            raise RuntimeError("simulated db failure")

        monkeypatch.setattr(
            "backend.interfaces.api.routes.health.SessionLocal",
            _raise,
        )
        app = create_app()
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "error"

    def test_worker_heartbeat_from_lease(self, monkeypatch, tmp_path):
        """存在未过期 RUNNING 租约时 worker_heartbeat=true。"""
        engine = create_engine(f"sqlite:///{tmp_path / 'health.db'}")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )
        with session_factory() as session:
            session.add(
                WorkerLeaseRecord(
                    worker_id="worker-1",
                    host="localhost",
                    pid=1,
                    status="RUNNING",
                    heartbeat_at=datetime(2026, 8, 7, 2, 0, 0),
                    lease_until=datetime.now(timezone.utc).replace(tzinfo=None)
                    + timedelta(minutes=5),
                )
            )
            session.commit()
        monkeypatch.setattr(
            "backend.interfaces.api.routes.health.SessionLocal", session_factory
        )

        response = TestClient(create_app()).get("/healthz")
        assert response.status_code == 200
        assert response.json()["worker_heartbeat"] is True

    def test_worker_heartbeat_false_without_lease(self, monkeypatch, tmp_path):
        """无活跃租约时 worker_heartbeat=false。"""
        engine = create_engine(f"sqlite:///{tmp_path / 'health-empty.db'}")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )
        monkeypatch.setattr(
            "backend.interfaces.api.routes.health.SessionLocal", session_factory
        )

        response = TestClient(create_app()).get("/healthz")
        assert response.status_code == 200
        assert response.json()["worker_heartbeat"] is False

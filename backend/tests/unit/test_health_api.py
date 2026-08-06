"""健康检查 API 测试。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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

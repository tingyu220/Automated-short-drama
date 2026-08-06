"""账户 API 集成测试 —— V1 not_configured 占位。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.interfaces.api.main import create_app


class TestAccountsApi:
    """账户概览 API 测试。"""

    def test_overview_returns_not_configured_placeholder(self):
        """V1 返回 not_configured 占位，不伪造飞书账户数据。"""
        app = create_app(dist_dir=None)
        with TestClient(app) as test_client:
            response = test_client.get("/api/accounts/overview")
        assert response.status_code == 200
        assert response.json() == {
            "sync_status": "not_configured",
            "last_synced_at": None,
            "accounts": [],
        }

"""平台登录态 API 集成测试。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.application.services.session_service import (
    STATUS_LOGGED_IN,
    SessionService,
)
from backend.interfaces.api.main import create_app
from backend.interfaces.api.routes import sessions as sessions_route


def test_list_sessions_reports_four_platforms(tmp_path):
    """GET /api/sessions 返回四平台登录态。"""
    service = SessionService(sessions_dir=tmp_path)

    def fake_service():
        return service

    sessions_route._service = fake_service
    app = create_app(dist_dir=None)
    client = TestClient(app)

    response = client.get("/api/sessions")

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"feishu", "tomato", "delivery", "ocean"}
    assert data["tomato"]["status"] == "needs_login"


def test_import_storage_and_check(tmp_path):
    """导入 storage 后 check 返回 logged_in。"""
    service = SessionService(sessions_dir=tmp_path)
    sessions_route._service = lambda: service
    app = create_app(dist_dir=None)
    client = TestClient(app)

    imported = client.post(
        "/api/sessions/tomato/storage",
        json={
            "storage_state": {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "x",
                        "domain": ".changdupingtai.com",
                    }
                ]
            }
        },
    )
    checked = client.post("/api/sessions/tomato/check")

    assert imported.status_code == 200
    assert checked.status_code == 200
    assert checked.json()["status"] == STATUS_LOGGED_IN


def test_login_and_finish_endpoints(tmp_path):
    """POST login/finish 委托登录管理器并返回运行状态。"""
    class FakeLoginManager:
        def start(self, platform: str) -> bool:
            return True

        def is_running(self, platform: str) -> bool:
            return True

        def finish(self, platform: str) -> bool:
            return True

    sessions_route._login_manager = FakeLoginManager()
    app = create_app(dist_dir=None)
    client = TestClient(app)

    login = client.post("/api/sessions/tomato/login")
    finish = client.post("/api/sessions/tomato/finish")

    assert login.status_code == 200
    assert login.json() == {
        "platform": "tomato",
        "started": True,
        "running": True,
    }
    assert finish.status_code == 200
    assert finish.json() == {"platform": "tomato", "finished": True}

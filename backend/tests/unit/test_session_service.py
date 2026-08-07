"""SessionService 单元测试：飞书 lark-cli 与本地 storage 检查。"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from backend.application.services.session_service import (
    STATUS_LOGGED_IN,
    STATUS_NEEDS_LOGIN,
    SessionService,
)


def _lark_result(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        stdout=json.dumps(payload, ensure_ascii=False),
        returncode=0,
    )


def _runner_with(payload: dict):
    def runner(*args, **kwargs):
        return _lark_result(payload)

    return runner


class TestFeishu:
    def test_logged_in_when_user_ready(self, tmp_path):
        service = SessionService(
            sessions_dir=tmp_path,
            runner=_runner_with(
                {
                    "identities": {
                        "user": {
                            "available": True,
                            "status": "ready",
                            "expiresAt": "2026-08-07T00:00:00+08:00",
                        }
                    }
                }
            ),
        )

        status = service.check("feishu")

        assert status.status == STATUS_LOGGED_IN
        assert status.expires_at is not None

    def test_needs_login_when_user_unavailable(self, tmp_path):
        service = SessionService(
            sessions_dir=tmp_path,
            runner=_runner_with(
                {
                    "identities": {
                        "user": {"available": False, "status": "unauthenticated"}
                    }
                }
            ),
        )

        status = service.check("feishu")

        assert status.status == STATUS_NEEDS_LOGIN

    def test_unknown_when_runner_raises(self, tmp_path):
        def runner(*args, **kwargs):
            raise OSError("lark-cli missing")

        service = SessionService(sessions_dir=tmp_path, runner=runner)

        assert service.check("feishu").status == "unknown"


class TestBrowserPlatforms:
    def test_no_storage_needs_login(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)

        assert service.check("tomato").status == STATUS_NEEDS_LOGIN
        assert service.check("delivery").status == STATUS_NEEDS_LOGIN
        assert service.check("ocean").status == STATUS_NEEDS_LOGIN

    def test_import_storage_then_logged_in(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        path = service.import_storage(
            "tomato",
            {"cookies": [{"name": "session", "value": "x"}]},
        )

        assert path.exists()
        status = service.check("tomato")
        assert status.status == STATUS_LOGGED_IN
        assert status.storage_path == str(path)

    def test_expired_cookie_needs_login(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "tomato",
            {"cookies": [{"name": "session", "expires": time.time() - 100}]},
        )

        status = service.check("tomato")

        assert status.status == STATUS_NEEDS_LOGIN
        assert "已过期" in status.message

    def test_session_cookie_without_expires_stays_logged_in(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "tomato",
            {"cookies": [{"name": "session"}]},
        )

        assert service.check("tomato").status == STATUS_LOGGED_IN

    def test_clear_removes_storage(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage("ocean", {"cookies": [{"name": "a"}]})

        service.clear("ocean")

        assert service.check("ocean").status == STATUS_NEEDS_LOGIN

    def test_unknown_platform_raises(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)

        with pytest.raises(ValueError):
            service.check("wechat")

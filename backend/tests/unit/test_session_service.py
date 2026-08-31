"""SessionService 单元测试：飞书 lark-cli 与本地 storage 检查。"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

import backend.application.services.session_service as session_service_module
from backend.application.services.session_service import (
    STATUS_LOGGED_IN,
    STATUS_NEEDS_LOGIN,
    SessionService,
)
from backend.application.services.session_service import _is_authenticated_probe_url


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
    def test_tomato_public_homepage_is_not_authenticated_probe(self):
        assert not _is_authenticated_probe_url(
            "tomato", "https://www.changdupingtai.com/page/home?show=true"
        )

    def test_tomato_sale_page_is_authenticated_probe(self):
        assert _is_authenticated_probe_url(
            "tomato", "https://www.changdupingtai.com/sale/short-play/list"
        )

    def test_check_live_rejects_cookie_when_delivery_page_redirects_to_login(
        self, tmp_path, monkeypatch
    ):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "delivery",
            {
                "cookies": [
                    {
                        "name": "Admin-Token",
                        "value": "stale",
                        "domain": "web.tjhaozew.top",
                    }
                ]
            },
        )
        monkeypatch.setattr(
            session_service_module,
            "_probe_browser_session",
            lambda platform, storage: (False, "页面已跳转到登录页"),
        )

        status = service.check_live("delivery")

        assert status.status == STATUS_NEEDS_LOGIN
        assert status.message == "页面已跳转到登录页"

    def test_no_storage_needs_login(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)

        assert service.check("tomato").status == STATUS_NEEDS_LOGIN
        assert service.check("delivery").status == STATUS_NEEDS_LOGIN
        assert service.check("ocean").status == STATUS_NEEDS_LOGIN

    def test_import_storage_then_logged_in(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        path = service.import_storage(
            "tomato",
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "x",
                        "domain": ".changdupingtai.com",
                    }
                ]
            },
        )

        assert path.exists()
        status = service.check("tomato")
        assert status.status == STATUS_LOGGED_IN
        assert status.storage_path == str(path)

    def test_expired_cookie_needs_login(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "tomato",
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "x",
                        "domain": ".changdupingtai.com",
                        "expires": time.time() - 100,
                    }
                ]
            },
        )

        status = service.check("tomato")

        assert status.status == STATUS_NEEDS_LOGIN
        assert "已过期" in status.message

    def test_session_cookie_without_expires_stays_logged_in(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "tomato",
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "x",
                        "domain": ".changdupingtai.com",
                    }
                ]
            },
        )

        assert service.check("tomato").status == STATUS_LOGGED_IN

    def test_session_cookie_with_minus_one_expires_stays_logged_in(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "tomato",
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "x",
                        "domain": ".changdupingtai.com",
                        "expires": -1,
                    }
                ]
            },
        )

        assert service.check("tomato").status == STATUS_LOGGED_IN

    def test_delivery_without_admin_token_needs_login(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "delivery",
            {"cookies": [{"name": "passport_trace_id", "domain": ".feishu.cn"}]},
        )

        status = service.check("delivery")

        assert status.status == STATUS_NEEDS_LOGIN
        assert "缺少平台认证凭证" in status.message

    def test_ocean_without_session_cookie_needs_login(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "ocean",
            {
                "cookies": [
                    {"name": "passport_csrf_token", "domain": ".oceanengine.com"},
                    {"name": "ttwid", "domain": ".oceanengine.com"},
                ]
            },
        )

        status = service.check("ocean")

        assert status.status == STATUS_NEEDS_LOGIN
        assert "缺少平台认证凭证" in status.message

    def test_delivery_admin_token_logged_in(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "delivery",
            {
                "cookies": [
                    {
                        "name": "Admin-Token",
                        "value": "jwt",
                        "domain": "web.tjhaozew.top",
                    }
                ]
            },
        )

        assert service.check("delivery").status == STATUS_LOGGED_IN

    def test_cookies_for_returns_stored_cookies(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "tomato",
            {"cookies": [{"name": "session", "value": "x"}]},
        )

        assert service.cookies_for("tomato") == [
            {"name": "session", "value": "x"}
        ]

    def test_import_storage_dedupes_and_keeps_new_cookie(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage(
            "ocean",
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "old",
                        "domain": ".oceanengine.com",
                        "path": "/",
                    }
                ]
            },
        )
        service.import_storage(
            "ocean",
            {
                "cookies": [
                    {
                        "name": "sessionid",
                        "value": "new",
                        "domain": ".oceanengine.com",
                        "path": "/",
                    }
                ]
            },
        )

        assert service.cookies_for("ocean")[0]["value"] == "new"

    def test_cookies_for_feishu_empty(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        assert service.cookies_for("feishu") == []

    def test_clear_removes_storage(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)
        service.import_storage("ocean", {"cookies": [{"name": "a"}]})

        service.clear("ocean")

        assert service.check("ocean").status == STATUS_NEEDS_LOGIN

    def test_unknown_platform_raises(self, tmp_path):
        service = SessionService(sessions_dir=tmp_path)

        with pytest.raises(ValueError):
            service.check("wechat")

"""Chrome Cookie 导入服务单元测试。"""
from __future__ import annotations

import pytest

from backend.application.services.chrome_cookie_importer import (
    ChromeCookieImportError,
    ChromeCookieImporter,
    _to_storage_cookie,
)
from backend.application.services.session_service import SessionService


def test_to_storage_cookie_converts_chrome_epoch():
    cookie = _to_storage_cookie(
        host_key=".oceanengine.com",
        name="sessionid",
        value="x",
        path="/",
        expires_utc=13300000000000000,
        has_expires=True,
        secure=True,
        http_only=True,
        same_site=-1,
    )

    assert cookie["domain"] == ".oceanengine.com"
    assert cookie["expires"] > 0
    assert cookie["httpOnly"] is True
    assert "sameSite" not in cookie


def test_to_storage_cookie_session_expires_negative():
    cookie = _to_storage_cookie(
        host_key="web.tjhaozew.top",
        name="Admin-Token",
        value="jwt",
        path="/",
        expires_utc=0,
        has_expires=False,
        secure=False,
        http_only=False,
        same_site=2,
    )

    assert cookie["expires"] == -1.0
    assert cookie["sameSite"] == "Strict"


def test_import_platform_writes_storage(tmp_path, monkeypatch):
    importer = ChromeCookieImporter(user_data_dir=tmp_path)
    cookies = [
        {
            "name": "sessionid",
            "value": "x",
            "domain": ".oceanengine.com",
            "path": "/",
            "expires": -1,
        }
    ]
    monkeypatch.setattr(
        importer,
        "read_platform_cookies",
        lambda platform: cookies,
    )
    service = SessionService(sessions_dir=tmp_path / "sessions")

    path, count = importer.import_platform("ocean", service)

    assert count == 1
    assert path.exists()
    assert service.check("ocean").status == "logged_in"


def test_import_platform_raises_without_cookies(tmp_path):
    importer = ChromeCookieImporter(user_data_dir=tmp_path)

    with pytest.raises(ChromeCookieImportError):
        importer.import_platform("ocean", SessionService(sessions_dir=tmp_path))

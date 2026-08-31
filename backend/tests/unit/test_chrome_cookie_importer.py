"""Chrome Cookie 导入服务单元测试。"""
from __future__ import annotations

import sqlite3

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


def test_read_profile_cookies_falls_back_to_read_only_when_chrome_file_is_locked(
    tmp_path, monkeypatch
):
    profile = tmp_path / "Default" / "Network"
    profile.mkdir(parents=True)
    source = profile / "Cookies"
    con = sqlite3.connect(source)
    con.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB, "
        "value TEXT, path TEXT, expires_utc INTEGER, is_secure INTEGER, "
        "is_httponly INTEGER, has_expires INTEGER, samesite INTEGER)"
    )
    con.execute(
        "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (".oceanengine.com", "sessionid", b"", "active", "/", 0, 1, 1, 0, -1),
    )
    con.commit()
    con.close()

    def locked_copy(*args, **kwargs):
        raise PermissionError("Chrome 正在使用 Cookies")

    monkeypatch.setattr("backend.application.services.chrome_cookie_importer.shutil.copy2", locked_copy)
    monkeypatch.setattr(
        "backend.application.services.chrome_cookie_importer._load_encryption_key",
        lambda _: b"test-key",
    )

    importer = ChromeCookieImporter(user_data_dir=tmp_path)
    cookies = importer.read_platform_cookies("ocean")

    assert cookies[0]["name"] == "sessionid"
    assert cookies[0]["value"] == "active"


def test_read_platform_cookies_reports_when_all_profiles_are_locked(tmp_path, monkeypatch):
    profile = tmp_path / "Default" / "Network"
    profile.mkdir(parents=True)
    (profile / "Cookies").touch()
    monkeypatch.setattr(
        "backend.application.services.chrome_cookie_importer._load_encryption_key",
        lambda _: b"test-key",
    )
    monkeypatch.setattr(
        "backend.application.services.chrome_cookie_importer._read_profile_cookies",
        lambda *args: (_ for _ in ()).throw(PermissionError("locked")),
    )

    with pytest.raises(ChromeCookieImportError, match="请关闭对应 Chrome"):
        ChromeCookieImporter(user_data_dir=tmp_path).read_platform_cookies("ocean")

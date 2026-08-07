"""SessionLoginManager 基础行为测试（不启动真实 Playwright）。"""
from __future__ import annotations

import pytest

from backend.application.services.session_login import (
    SessionLoginManager,
    _verify_generic_logged_in,
)


def test_finish_without_running_returns_false(tmp_path):
    manager = SessionLoginManager(sessions_dir=tmp_path)

    assert manager.is_running("tomato") is False
    assert manager.finish("tomato") is False


def test_start_unsupported_platform_raises(tmp_path):
    manager = SessionLoginManager(sessions_dir=tmp_path)

    with pytest.raises(ValueError):
        manager.start("feishu")


def test_storage_path_under_sessions_dir(tmp_path):
    manager = SessionLoginManager(sessions_dir=tmp_path)

    assert manager.storage_path("tomato") == (
        tmp_path / "tomato" / "storage.json"
    )


class FakePage:
    def __init__(self, url: str = "", body: str = "") -> None:
        self.url = url
        self.body = body

    def goto(self, *args, **kwargs) -> None:
        pass

    def wait_for_timeout(self, *args, **kwargs) -> None:
        pass

    def inner_text(self, selector: str) -> str:
        return self.body

    def close(self) -> None:
        pass


class FakeContext:
    def __init__(self, cookies: list[dict], page: FakePage) -> None:
        self._cookies = cookies
        self._page = page

    def cookies(self) -> list[dict]:
        return self._cookies

    def new_page(self) -> FakePage:
        return self._page


def test_verify_rejects_missing_auth_cookie():
    context = FakeContext(
        cookies=[{"name": "passport_csrf_token", "domain": ".oceanengine.com"}],
        page=FakePage(url="https://business.oceanengine.com/brand/index"),
    )

    assert _verify_generic_logged_in("ocean", context) is False


def test_verify_rejects_redirect_back_to_login_page():
    context = FakeContext(
        cookies=[
            {
                "name": "Admin-Token",
                "value": "jwt",
                "domain": "web.tjhaozew.top",
            }
        ],
        page=FakePage(
            url="http://web.tjhaozew.top/login?redirect=%2Fjuliangg%2Fv2",
            body="短剧投放系统\n飞书授权登录",
        ),
    )

    assert _verify_generic_logged_in("delivery", context) is False


def test_verify_passes_with_auth_cookie_and_home_page():
    context = FakeContext(
        cookies=[
            {
                "name": "Admin-Token",
                "value": "jwt",
                "domain": "web.tjhaozew.top",
            }
        ],
        page=FakePage(
            url="http://web.tjhaozew.top/juliangg/v2",
            body="短剧投放系统\n广告管理\n巨量引擎V2",
        ),
    )

    assert _verify_generic_logged_in("delivery", context) is True

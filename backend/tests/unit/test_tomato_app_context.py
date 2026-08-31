from __future__ import annotations

import pytest

from backend.domain.errors.domain_error import ExternalAdapterError
from backend.platforms.tomato.page_objects.app_context import AppContextPage


class _MissingContextLocator:
    def text_content(self):
        raise RuntimeError("context locator missing")


class _MissingContextPage:
    url = "https://www.changdupingtai.com/page/home?show=true"

    def locator(self, selector: str):
        return _MissingContextLocator()


SELECTORS = {
    "free_comic_app_name": "抖音端原生免费漫剧",
    "paid_comic_app_name": "抖音端原生付费漫剧",
    "expected_channel_name": "李伟",
    "app_context_value": ".context",
    "app_cascader": ".cascader",
    "app_option": ".option",
    "default_app_name": "默认应用",
}


def test_public_homepage_reports_login_required():
    with pytest.raises(ExternalAdapterError) as caught:
        AppContextPage(_MissingContextPage(), SELECTORS).ensure("PAID")

    assert caught.value.code == "TOMATO_LOGIN_REQUIRED"

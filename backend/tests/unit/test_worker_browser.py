"""Automation Worker 单浏览器会话测试。"""
from __future__ import annotations

import json
from pathlib import Path

from backend.infrastructure.browser.worker_browser import (
    WorkerBrowserSession,
    _is_playwright_chrome_cmd,
    cleanup_zombie_browsers,
    load_worker_storage_state,
)


def test_load_worker_storage_state_merges_platform_cookies(tmp_path: Path) -> None:
    """同一浏览器上下文必须同时装载番茄和投放系统登录态。"""
    tomato = tmp_path / "tomato"
    delivery = tmp_path / "delivery"
    tomato.mkdir()
    delivery.mkdir()
    (tomato / "storage.json").write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "sid", "domain": "tomato.test", "path": "/", "value": "t"}
                ],
                "origins": [{"origin": "https://tomato.test", "localStorage": []}],
            }
        ),
        encoding="utf-8",
    )
    (delivery / "storage.json").write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": "token", "domain": "delivery.test", "path": "/", "value": "d"}
                ],
                "origins": [{"origin": "https://delivery.test", "localStorage": []}],
            }
        ),
        encoding="utf-8",
    )

    state = load_worker_storage_state(tmp_path)

    assert [cookie["name"] for cookie in state["cookies"]] == ["sid", "token"]
    assert [origin["origin"] for origin in state["origins"]] == [
        "https://tomato.test",
        "https://delivery.test",
    ]


def test_load_worker_storage_state_rejects_broken_json(tmp_path: Path) -> None:
    tomato = tmp_path / "tomato"
    tomato.mkdir()
    (tomato / "storage.json").write_text("not-json", encoding="utf-8")

    try:
        load_worker_storage_state(tmp_path)
    except ValueError as exc:
        assert "登录态文件损坏" in str(exc)
    else:
        raise AssertionError("损坏的登录态必须阻止真实 Worker 启动")


def test_worker_browser_reuses_one_page_and_closes_resources(tmp_path: Path) -> None:
    calls: list[object] = []
    page = object()

    class Context:
        def new_page(self):
            calls.append("new_page")
            return page

        def close(self):
            calls.append("context_close")

    class Browser:
        def new_context(
            self,
            *,
            storage_state,
            ignore_https_errors=False,
            permissions=None,
        ):
            calls.append(("storage_state", storage_state))
            return Context()

        def close(self):
            calls.append("browser_close")

    class Chromium:
        def launch(self, *, headless, args):
            calls.append(("launch", headless, args))
            return Browser()

    class Playwright:
        chromium = Chromium()

        def stop(self):
            calls.append("playwright_stop")

    class Manager:
        def start(self):
            calls.append("playwright_start")
            return Playwright()

    runtime = WorkerBrowserSession(
        sessions_dir=tmp_path,
        playwright_factory=lambda: Manager(),
    )

    assert runtime.start() is page
    assert runtime.start() is page
    runtime.close()

    assert calls[0] == "playwright_start"
    assert calls[1][0] == "launch"
    assert calls[1][1] is True  # headless
    assert isinstance(calls[1][2], list)  # args
    assert "--no-sandbox" in calls[1][2]
    assert "--disable-dev-shm-usage" in calls[1][2]
    assert calls[2] == ("storage_state", {"cookies": [], "origins": []})
    assert calls[3] == "new_page"
    assert calls[4] == "context_close"
    assert calls[5] == "browser_close"
    assert calls[6] == "playwright_stop"


def test_worker_browser_rebuilds_page_after_user_closes_browser(tmp_path: Path) -> None:
    """用户关闭浏览器窗口后，下一次启动必须创建新的页面。"""
    calls: list[str] = []

    class Page:
        def __init__(self) -> None:
            self.closed = False

        def is_closed(self) -> bool:
            return self.closed

    pages: list[Page] = []

    class Context:
        def new_page(self):
            calls.append("new_page")
            page = Page()
            pages.append(page)
            return page

        def close(self):
            calls.append("context_close")

    class Browser:
        def new_context(
            self,
            *,
            storage_state,
            ignore_https_errors=False,
            permissions=None,
        ):
            return Context()

        def close(self):
            calls.append("browser_close")

        def is_connected(self) -> bool:
            return True

    class Chromium:
        def launch(self, *, headless, args):
            return Browser()

    class Playwright:
        chromium = Chromium()

        def stop(self):
            calls.append("playwright_stop")

    class Manager:
        def start(self):
            return Playwright()

    runtime = WorkerBrowserSession(
        sessions_dir=tmp_path,
        playwright_factory=lambda: Manager(),
    )

    first_page = runtime.start()
    pages[0].closed = True
    second_page = runtime.start()

    assert second_page is not first_page
    assert calls == [
        "new_page",
        "context_close",
        "browser_close",
        "playwright_stop",
        "new_page",
    ]


def test_is_playwright_chrome_cmd_recognizes_playwright_browser() -> None:
    """含 headless + remote-debugging-port 的命令行应被识别为 Playwright 浏览器。"""
    assert _is_playwright_chrome_cmd(
        "chrome.exe --headless --remote-debugging-port=0 --no-sandbox"
    ) is True
    assert _is_playwright_chrome_cmd(
        "/usr/bin/chromium --headless=new --remote-debugging-port=1234"
    ) is True


def test_is_playwright_chrome_cmd_ignores_normal_browser() -> None:
    """普通用户浏览器不应被误识别。"""
    assert _is_playwright_chrome_cmd(
        "chrome.exe --restore-last-session"
    ) is False
    assert _is_playwright_chrome_cmd(
        "chrome.exe --type=renderer --lang=zh-CN"
    ) is False
    assert _is_playwright_chrome_cmd("") is False
    assert _is_playwright_chrome_cmd(None) is False  # type: ignore[arg-type]


def test_is_playwright_chrome_cmd_requires_both_markers() -> None:
    """只含 headless 或只含 remote-debugging-port 都不算。"""
    assert _is_playwright_chrome_cmd(
        "chrome.exe --headless --disable-gpu"
    ) is False
    assert _is_playwright_chrome_cmd(
        "chrome.exe --remote-debugging-port=9222"
    ) is False


def test_cleanup_zombie_browsers_does_not_crash() -> None:
    """清理函数在任何平台都不应抛异常。"""
    # 只验证不抛错，不验证实际效果（依赖运行环境）
    result = cleanup_zombie_browsers()
    assert isinstance(result, int)

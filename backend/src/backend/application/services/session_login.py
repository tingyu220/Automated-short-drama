"""后台平台登录任务：Playwright 持久化登录并自动保存 Session。"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.application.services.session_service import (
    PLATFORM_LOGIN_URLS,
    SessionService,
)
from backend.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

_TOMATO_HOME_URL = "https://www.changdupingtai.com/page/home?show=true"
_TOMATO_LOGGED_IN_SELECTORS = (
    ".layout-menus-cascader",
    ".arco-cascader-view",
    "a[href*='/sale/short-play/list']",
    "a[href*='/sale/novel/list']",
)
_LOGIN_WAIT_SECONDS = 600
_LOGIN_PAGE_TEXT: dict[str, tuple[str, ...]] = {
    "delivery": ("请登录", "未登录", "飞书授权登录"),
    "ocean": ("请登录", "未登录"),
    "youxuan": ("请登录", "未登录"),
}


@dataclass
class _LoginTask:
    running: bool = True
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    user_confirmed: bool = False


class SessionLoginManager:
    """按平台启动/结束 Playwright 登录任务。"""

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._service = SessionService(sessions_dir=sessions_dir)
        self._tasks: dict[str, _LoginTask] = {}
        self._lock = threading.Lock()

    def start(self, platform: str) -> bool:
        """启动登录任务；已有运行中任务返回 False。"""
        if platform not in PLATFORM_LOGIN_URLS or platform == "feishu":
            raise ValueError(f"平台不支持网页登录: {platform}")
        with self._lock:
            existing = self._tasks.get(platform)
            if existing and existing.running:
                return False
            task = _LoginTask()
            self._tasks[platform] = task
        thread = threading.Thread(
            target=self._run,
            args=(platform, task),
            daemon=True,
            name=f"session-login-{platform}",
        )
        task.thread = thread
        thread.start()
        return True

    def finish(self, platform: str) -> bool:
        """用户确认已登录，触发立即保存。"""
        with self._lock:
            task = self._tasks.get(platform)
            if not task:
                return False
            if not task.running:
                task.running = False
                return False
            task.user_confirmed = True
            task.stop.set()
            return True

    def is_running(self, platform: str) -> bool:
        with self._lock:
            task = self._tasks.get(platform)
            return bool(task and task.running)

    def reset(self, platform: str) -> bool:
        """强制重置登录状态（用于浏览器崩溃后按钮卡住）。"""
        with self._lock:
            task = self._tasks.get(platform)
            if task:
                task.running = False
                task.stop.set()
                self._tasks.pop(platform, None)
            return True

    def storage_path(self, platform: str) -> Path:
        return self._service.storage_path(platform)

    def _run(self, platform: str, task: _LoginTask) -> None:
        """在后台线程打开 Playwright 持久化浏览器完成登录。"""
        from playwright.sync_api import sync_playwright

        user_data_dir = Settings().data_dir / "sessions" / platform / "profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=False,
                    viewport={"width": 1400, "height": 900},
                    ignore_https_errors=True,
                )
                try:
                    ok = _login_page(platform, context, task.stop)
                    if ok or task.user_confirmed:
                        _save_storage(context, self.storage_path(platform))
                finally:
                    context.close()
        except Exception:
            logger.exception("平台登录任务异常: platform=%s", platform)
        finally:
            task.running = False


def _login_page(platform: str, context, stop: threading.Event) -> bool:
    """按平台执行登录；仅在校验通过后返回 True。"""
    if platform == "tomato":
        return _login_tomato(context, stop)
    return _login_generic(platform, context, stop)


def _login_tomato(context, stop: threading.Event) -> bool:
    """番茄登录：首页弹窗 + 自动填账密 + 验证码人工完成。"""
    page = context.new_page()
    page.goto(_TOMATO_HOME_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)
    if _tomato_logged_in(page):
        return True

    login_btn = page.locator("span").filter(has_text="登录").first
    if login_btn.count():
        login_btn.click()
        page.wait_for_timeout(2000)
    _fill_tomato_credentials(page)

    deadline = time.time() + _LOGIN_WAIT_SECONDS
    while time.time() < deadline:
        if _tomato_logged_in(page):
            return True
        if stop.is_set():
            return False
        time.sleep(2)
    return False


def _fill_tomato_credentials(page) -> None:
    """从 Settings/.env 读取账密并自动填写。"""
    settings = Settings()
    account = (settings.changdu_account or "").strip()
    password = (settings.changdu_password or "").strip()
    if not account or not password:
        return
    email = page.query_selector(
        "input[name='email'], input[placeholder*='邮箱']"
    )
    pw = page.query_selector("input[type='password']")
    if not email or not pw:
        return
    email.fill(account)
    pw.fill(password)
    for checkbox in page.locator("input[type='checkbox']").all():
        try:
            checkbox.check()
        except Exception:
            pass
    page.wait_for_timeout(500)
    submit = page.query_selector("button:has-text('登录')")
    if submit:
        try:
            page.eval_on_selector(
                "button:has-text('登录')",
                "el => el.disabled = false",
            )
        except Exception:
            pass
        submit.click()
        page.wait_for_timeout(10000)


def _tomato_logged_in(page) -> bool:
    for selector in _TOMATO_LOGGED_IN_SELECTORS:
        if page.query_selector(selector):
            return True
    return False


def _login_generic(platform: str, context, stop: threading.Event) -> bool:
    """投放/巨量通用登录：候选信号触发后需通过页面回访校验。"""
    page = context.new_page()
    page.goto(PLATFORM_LOGIN_URLS[platform], wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    initial_keys = _cookie_keys(context)
    deadline = time.time() + _LOGIN_WAIT_SECONDS
    while time.time() < deadline:
        if stop.is_set():
            return _verify_generic_logged_in(platform, context)
        current_keys = _cookie_keys(context)
        url = page.url.lower()
        if current_keys - initial_keys or (
            url
            and "login" not in url
            and "login" in PLATFORM_LOGIN_URLS[platform]
        ):
            if _verify_generic_logged_in(platform, context):
                return True
            time.sleep(2)
        time.sleep(2)
    return False


def _verify_generic_logged_in(platform: str, context) -> bool:
    """回访平台页面，确认会话未被重定向到登录页。"""
    probe = context.new_page()
    try:
        probe.goto(
            PLATFORM_LOGIN_URLS[platform],
            wait_until="domcontentloaded",
            timeout=30000,
        )
        probe.wait_for_timeout(2000)
        url = probe.url.lower()
        if "login" in url or "auth" in url or "feishu.cn" in url:
            return False
        body = probe.inner_text("body") or ""
        markers = _LOGIN_PAGE_TEXT.get(platform, ())
        if any(marker in body for marker in markers):
            return False
        return True
    except Exception:
        logger.exception("平台登录校验失败: platform=%s", platform)
        return False
    finally:
        probe.close()


def _cookie_keys(context) -> set[tuple[str, str]]:
    return {
        (cookie["name"], cookie.get("domain", ""))
        for cookie in context.cookies()
    }


def _save_storage(context, storage_path: Path) -> None:
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(storage_path))
    logger.info("平台登录态已保存: path=%s", storage_path)

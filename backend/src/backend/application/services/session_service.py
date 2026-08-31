"""平台登录态管理：手动登录 + 本地持久化 Session。"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

STATUS_LOGGED_IN = "logged_in"
STATUS_NEEDS_LOGIN = "needs_login"
STATUS_UNKNOWN = "unknown"

PLATFORM_LOGIN_URLS: dict[str, str] = {
    "feishu": "https://open.feishu.cn/document/client-docs/authentication/",
    "tomato": "https://www.changdupingtai.com/page/home?show=true",
    "delivery": "http://web.tjhaozew.top/juliangg/v2",
    "ocean": "https://business.oceanengine.com",
}

_LIVE_PROBE_URLS: dict[str, str] = {
    **PLATFORM_LOGIN_URLS,
    "tomato": "https://www.changdupingtai.com/sale/short-play/list",
    "delivery": "http://web.tjhaozew.top/video/dramas",
}

AUTH_COOKIE_NAMES: dict[str, set[str]] = {
    "tomato": {"sessionid", "sid_guard", "username", "nickName"},
    "delivery": {"Admin-Token"},
    "ocean": {
        "sessionid",
        "sessionid_ss",
        "sid_guard",
        "sid_tt",
        "uid_tt",
        "uid_tt_ss",
    },
}


@dataclass(frozen=True)
class SessionStatus:
    """单个平台登录态。"""

    platform: str
    status: str
    login_url: str
    message: str = ""
    expires_at: str | None = None
    storage_path: str | None = None


class SessionService:
    """检查与保存四平台登录态；Cookie/Session 只落 data/sessions，不入库。"""

    def __init__(
        self,
        sessions_dir: Path | None = None,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self._sessions_dir = sessions_dir or (
            Settings().data_dir / "sessions"
        )
        self._runner = runner

    def list_statuses(self) -> dict[str, dict]:
        """返回全部平台登录态。"""
        return {
            platform: (
                self._check_feishu() if platform == "feishu" else self.check_live(platform)
            ).__dict__
            for platform in PLATFORM_LOGIN_URLS
        }

    def check(self, platform: str) -> SessionStatus:
        """检查单个平台登录态。"""
        if platform not in PLATFORM_LOGIN_URLS:
            raise ValueError(f"不支持的平台: {platform}")
        if platform == "feishu":
            return self._check_feishu()
        return self._check_browser_session(platform)

    def check_live(self, platform: str) -> SessionStatus:
        """检查本地登录态后访问平台页面，确认会话未被重定向到登录页。"""
        status = self.check(platform)
        if status.status != STATUS_LOGGED_IN or platform == "feishu":
            return status

        storage = self._load_storage(platform)
        active, message = _probe_browser_session(platform, _sanitize_storage(storage))
        if active is True:
            return SessionStatus(
                platform=status.platform,
                status=STATUS_LOGGED_IN,
                login_url=status.login_url,
                message=message,
                expires_at=status.expires_at,
                storage_path=status.storage_path,
            )
        if active is False:
            return SessionStatus(
                platform=status.platform,
                status=STATUS_NEEDS_LOGIN,
                login_url=status.login_url,
                message=message,
                expires_at=status.expires_at,
                storage_path=status.storage_path,
            )
        return SessionStatus(
            platform=status.platform,
            status=STATUS_UNKNOWN,
            login_url=status.login_url,
            message=message,
            expires_at=status.expires_at,
            storage_path=status.storage_path,
        )

    def import_storage(self, platform: str, storage_state: dict) -> Path:
        """把浏览器导出的 storage_state 合并写入 data/sessions/<platform>/storage.json。"""
        if platform not in PLATFORM_LOGIN_URLS or platform == "feishu":
            raise ValueError(f"平台不支持 storage 导入: {platform}")
        path = self.storage_path(platform)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._load_storage(platform)
        incoming_cookies = storage_state.get("cookies", [])
        cookies = _dedupe_cookies(
            incoming_cookies + existing.get("cookies", [])
        )
        merged = {
            "cookies": cookies,
            "origins": existing.get("origins", []) + storage_state.get("origins", []),
        }
        path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("已保存登录态: platform=%s path=%s", platform, path)
        return path

    def clear(self, platform: str) -> None:
        """删除单个平台本地 Session 文件（调用方先备份）。"""
        if platform not in PLATFORM_LOGIN_URLS:
            raise ValueError(f"不支持的平台: {platform}")
        path = self.storage_path(platform)
        if path.exists():
            path.unlink()

    def storage_path(self, platform: str) -> Path:
        """返回平台 storage_state 文件路径。"""
        return self._sessions_dir / platform / "storage.json"

    def cookies_for(self, platform: str) -> list[dict]:
        """返回平台已持久化 Cookie（供 Playwright context 加载）。"""
        if platform not in PLATFORM_LOGIN_URLS or platform == "feishu":
            return []
        storage = self._load_storage(platform)
        cookies = storage.get("cookies") or []
        return [
            cookie
            for cookie in cookies
            if isinstance(cookie, dict) and cookie.get("name")
        ]

    def _check_feishu(self) -> SessionStatus:
        """飞书登录态来自 lark-cli auth status。"""
        try:
            result = self._runner(
                _lark_auth_command(),
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = json.loads(result.stdout)
            user = (data.get("identities") or {}).get("user") or {}
            available = user.get("available") is True
            status = str(user.get("status", ""))
            if available and status in ("ready", "needs_refresh"):
                return SessionStatus(
                    platform="feishu",
                    status=STATUS_LOGGED_IN,
                    login_url=PLATFORM_LOGIN_URLS["feishu"],
                    message=user.get("message") or "飞书用户身份可用",
                    expires_at=user.get("expiresAt"),
                )
            return SessionStatus(
                platform="feishu",
                status=STATUS_NEEDS_LOGIN,
                login_url=PLATFORM_LOGIN_URLS["feishu"],
                message="飞书用户身份未认证",
            )
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            logger.warning("飞书登录态检查失败: %s", exc)
            return SessionStatus(
                platform="feishu",
                status=STATUS_UNKNOWN,
                login_url=PLATFORM_LOGIN_URLS["feishu"],
                message="无法读取 lark-cli 登录态",
            )

    def _check_browser_session(self, platform: str) -> SessionStatus:
        """网页平台登录态：存在未过期平台认证 Cookie 才算已登录。"""
        path = self.storage_path(platform)
        storage = self._load_storage(platform)
        cookies = storage.get("cookies") or []
        now = time.time()
        unexpired = [cookie for cookie in cookies if _cookie_is_active(cookie, now)]
        if path.exists() and unexpired and has_platform_auth_cookie(
            unexpired, platform
        ):
            return SessionStatus(
                platform=platform,
                status=STATUS_LOGGED_IN,
                login_url=PLATFORM_LOGIN_URLS[platform],
                message="本地 Session 已持久化并校验",
                storage_path=str(path),
            )
        if path.exists() and cookies:
            has_auth = has_platform_auth_cookie(cookies, platform)
            return SessionStatus(
                platform=platform,
                status=STATUS_NEEDS_LOGIN,
                login_url=PLATFORM_LOGIN_URLS[platform],
                message=(
                    "本地登录态缺少平台认证凭证，请重新登录"
                    if not has_auth
                    else "本地登录态已过期，请重新登录"
                ),
                storage_path=str(path),
            )
        return SessionStatus(
            platform=platform,
            status=STATUS_NEEDS_LOGIN,
            login_url=PLATFORM_LOGIN_URLS[platform],
            message="需要手动登录并持久化 Session",
            storage_path=str(path) if path.exists() else None,
        )

    def _load_storage(self, platform: str) -> dict[str, Any]:
        path = self.storage_path(platform)
        if not path.exists():
            return {"cookies": [], "origins": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            logger.warning("登录态文件损坏: %s", path)
        return {"cookies": [], "origins": []}


def _lark_auth_command() -> list[str]:
    """返回可执行的 lark-cli auth status 命令（兼容 Windows npm shim）。"""
    resolved = shutil.which("lark-cli") or shutil.which("lark-cli.cmd")
    if resolved and resolved.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", "lark-cli", "auth", "status"]
    return ["lark-cli", "auth", "status"]


def has_platform_auth_cookie(cookies: list[dict], platform: str) -> bool:
    """判断 Cookie 中是否含平台登录后才会出现的认证凭证。"""
    names = AUTH_COOKIE_NAMES.get(platform, set())
    if not names:
        return False
    host = PLATFORM_LOGIN_URLS[platform].split("://", 1)[-1].split("/", 1)[0].lower()
    for cookie in cookies:
        if cookie.get("name") not in names:
            continue
        domain = str(cookie.get("domain") or "").lower().lstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return True
    return False


_LOGIN_PAGE_TEXT: dict[str, tuple[str, ...]] = {
    "tomato": ("请登录", "未登录"),
    "delivery": ("请登录", "未登录", "飞书授权登录"),
    "ocean": ("请登录", "未登录"),
}


def _probe_browser_session(
    platform: str, storage: dict[str, Any]
) -> tuple[bool | None, str]:
    """用独立无头页面探测真实访问结果，不写入登录态文件。"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    storage_state=storage,
                    ignore_https_errors=True,
                )
                try:
                    page = context.new_page()
                    resp = page.goto(
                        _LIVE_PROBE_URLS[platform],
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    page.wait_for_timeout(1000)
                    url = page.url.lower()
                    body = page.inner_text("body") or ""
                    if resp and resp.status >= 500:
                        return None, f"服务器错误 (HTTP {resp.status})，无法判断登录态"
                    if not _is_authenticated_probe_url(platform, url):
                        return False, "页面已跳转到登录页"
                    if any(marker in body for marker in _LOGIN_PAGE_TEXT[platform]):
                        return False, "页面显示未登录"
                    if "500" in body and "Internal Server Error" in body:
                        return None, "服务器返回 500 错误，无法判断登录态"
                    return True, "实时页面校验通过"
                finally:
                    context.close()
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("平台实时登录态检查失败: platform=%s error=%s", platform, exc)
        return None, "实时校验失败，请检查网络或稍后重试"


def _is_authenticated_probe_url(platform: str, url: str) -> bool:
    """判断实时探测是否仍停留在平台受保护页面。"""
    lowered = url.lower()
    if "login" in lowered or "auth" in lowered:
        return False
    if platform == "tomato":
        return "/sale/" in lowered
    if platform == "delivery":
        return "/video/dramas" in lowered or "/autotask" in lowered
    return True


def _dedupe_cookies(cookies: list[dict]) -> list[dict]:
    """按 name/domain/path 去重，新导入的 Cookie 优先。"""
    seen: set[tuple[str, str, str]] = set()
    result: list[dict] = []
    for cookie in cookies:
        key = (
            str(cookie.get("name") or ""),
            str(cookie.get("domain") or ""),
            str(cookie.get("path") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(cookie)
    return result


_VALID_SAMESITE = {"Strict", "Lax", "None"}


def _sanitize_storage(storage: dict[str, Any]) -> dict[str, Any]:
    """清洗 storage_state 中的 cookie，确保 Playwright 兼容。"""
    cookies = storage.get("cookies") or []
    sanitized: list[dict] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain")
        if not name or not isinstance(name, str):
            continue
        if value is None or not isinstance(value, str):
            continue
        if not domain or not isinstance(domain, str):
            continue
        path = cookie.get("path")
        if not path or not isinstance(path, str):
            path = "/"
        result: dict = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
        }
        expires = cookie.get("expires")
        if isinstance(expires, (int, float)):
            result["expires"] = float(expires)
        else:
            result["expires"] = -1.0
        if cookie.get("httpOnly") is not None:
            result["httpOnly"] = bool(cookie["httpOnly"])
        if cookie.get("secure") is not None:
            result["secure"] = bool(cookie["secure"])
        same_site = cookie.get("sameSite")
        if isinstance(same_site, str) and same_site in _VALID_SAMESITE:
            result["sameSite"] = same_site
        sanitized.append(result)
    return {"cookies": sanitized, "origins": storage.get("origins") or []}


def _cookie_is_active(cookie: dict, now: float) -> bool:
    """Session Cookie（无过期时间）视为有效，过期时间戳为 -1 也视为有效。"""
    expires = cookie.get("expires")
    if expires is None:
        return True
    try:
        return float(expires) < 0 or float(expires) >= now
    except (TypeError, ValueError):
        return True

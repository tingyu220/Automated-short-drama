"""平台登录态管理：手动登录 + 本地持久化 Session。"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
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
    "tomato": "https://www.changdunovel.com/sale/login?show=true",
    "delivery": "http://web.tjhaozew.top/juliangg/v2",
    "ocean": "https://business.oceanengine.com",
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
            platform: self.check(platform).__dict__
            for platform in PLATFORM_LOGIN_URLS
        }

    def check(self, platform: str) -> SessionStatus:
        """检查单个平台登录态。"""
        if platform not in PLATFORM_LOGIN_URLS:
            raise ValueError(f"不支持的平台: {platform}")
        if platform == "feishu":
            return self._check_feishu()
        return self._check_browser_session(platform)

    def import_storage(self, platform: str, storage_state: dict) -> Path:
        """把浏览器导出的 storage_state 合并写入 data/sessions/<platform>/storage.json。"""
        if platform not in PLATFORM_LOGIN_URLS or platform == "feishu":
            raise ValueError(f"平台不支持 storage 导入: {platform}")
        path = self.storage_path(platform)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._load_storage(platform)
        merged = {
            "cookies": existing.get("cookies", []) + storage_state.get("cookies", []),
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
        """网页平台登录态：storage.json 存在且含 Cookie 视为已持久化。"""
        path = self.storage_path(platform)
        storage = self._load_storage(platform)
        has_cookies = bool(storage.get("cookies"))
        if path.exists() and has_cookies:
            return SessionStatus(
                platform=platform,
                status=STATUS_LOGGED_IN,
                login_url=PLATFORM_LOGIN_URLS[platform],
                message="本地 Session 已持久化",
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

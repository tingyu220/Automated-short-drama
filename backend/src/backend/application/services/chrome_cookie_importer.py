"""从本机 Chrome 读取登录 Cookie 并导入平台 Session。"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.application.services.session_service import (
    AUTH_COOKIE_NAMES,
    SessionService,
)

logger = logging.getLogger(__name__)

_PLATFORM_DOMAINS: dict[str, str] = {
    "tomato": "changdupingtai.com",
    "delivery": "tjhaozew.top",
    "ocean": "oceanengine.com",
}
_SAME_SITE_MAP: dict[int, str | None] = {
    -1: None,
    0: "None",
    1: "Lax",
    2: "Strict",
}
_CHROME_EPOCH_OFFSET = 11644473600
SUPPORTED_PLATFORMS = tuple(_PLATFORM_DOMAINS)


class ChromeCookieImportError(RuntimeError):
    """Chrome Cookie 读取或导入失败。"""


class ChromeCookieImporter:
    """扫描本机 Chrome 配置，导入指定平台的登录 Cookie。"""

    def __init__(self, user_data_dir: Path | None = None) -> None:
        self._user_data_dir = user_data_dir or _default_chrome_dir()

    def import_platform(
        self,
        platform: str,
        service: SessionService | None = None,
    ) -> tuple[Path, int]:
        """读取指定平台 Cookie 并写入 Session 文件，返回路径与数量。"""
        cookies = self.read_platform_cookies(platform)
        if not cookies:
            raise ChromeCookieImportError(
                f"Chrome 中未找到 {platform} 平台登录 Cookie"
            )
        session_service = service or SessionService()
        path = session_service.import_storage(platform, {"cookies": cookies})
        logger.info(
            "已从 Chrome 导入登录态: platform=%s cookies=%d path=%s",
            platform,
            len(cookies),
            path,
        )
        return path, len(cookies)

    def read_platform_cookies(self, platform: str) -> list[dict[str, Any]]:
        """按配置目录顺序返回首个含平台认证 Cookie 的配置。"""
        if platform not in _PLATFORM_DOMAINS:
            raise ChromeCookieImportError(f"不支持的平台: {platform}")
        domain = _PLATFORM_DOMAINS[platform]
        auth_names = AUTH_COOKIE_NAMES.get(platform, set())
        key = _load_encryption_key(self._user_data_dir)
        for profile_dir in _chrome_profiles(self._user_data_dir):
            try:
                cookies = _read_profile_cookies(profile_dir, key, domain)
            except (OSError, sqlite3.DatabaseError, ChromeCookieImportError) as exc:
                logger.warning("读取 Chrome 配置失败: %s %s", profile_dir, exc)
                continue
            if cookies and any(
                cookie.get("name") in auth_names for cookie in cookies
            ):
                return cookies
        return []


def _default_chrome_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Google" / "Chrome" / "User Data"


def _chrome_profiles(user_data_dir: Path):
    default = user_data_dir / "Default"
    if (default / "Network" / "Cookies").exists():
        yield default
    if not user_data_dir.exists():
        return
    for child in sorted(user_data_dir.iterdir(), key=lambda p: p.name):
        if (
            child.is_dir()
            and child.name.startswith("Profile ")
            and (child / "Network" / "Cookies").exists()
        ):
            yield child


def _load_encryption_key(user_data_dir: Path) -> bytes:
    local_state = user_data_dir / "Local State"
    if not local_state.exists():
        raise ChromeCookieImportError("未找到 Chrome Local State")
    try:
        from win32crypt import CryptUnprotectData
    except ImportError as exc:
        raise ChromeCookieImportError("缺少 pywin32，无法解密 Chrome Cookie") from exc
    data = json.loads(local_state.read_text(encoding="utf-8"))
    blob = base64.b64decode(data["os_crypt"]["encrypted_key"])
    if blob.startswith(b"DPAPI"):
        blob = blob[5:]
    _, key = CryptUnprotectData(blob, None, None, None, 0)
    return key


def _read_profile_cookies(
    profile_dir: Path,
    key: bytes,
    domain: str,
) -> list[dict[str, Any]]:
    source = profile_dir / "Network" / "Cookies"
    if not source.exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = Path(tmp) / "Cookies"
        shutil.copy2(source, copy_path)
        con = sqlite3.connect(copy_path)
        try:
            columns = {
                row[1] for row in con.execute("PRAGMA table_info(cookies)")
            }
            required = {
                "host_key",
                "name",
                "encrypted_value",
                "value",
                "path",
                "expires_utc",
                "is_secure",
                "is_httponly",
                "has_expires",
            }
            if not required.issubset(columns):
                return []
            select = (
                "host_key,name,encrypted_value,value,path,expires_utc,"
                "is_secure,is_httponly,has_expires"
            )
            if "top_frame_site_key" in columns:
                select += ",top_frame_site_key"
            if "samesite" in columns:
                select += ",samesite"
            rows = con.execute(f"SELECT {select} FROM cookies").fetchall()
        finally:
            con.close()

    cookies: list[dict[str, Any]] = []
    for row in rows:
        (
            host_key,
            name,
            encrypted_value,
            plain_value,
            path,
            expires_utc,
            is_secure,
            is_httponly,
            has_expires,
        ) = row[:9]
        top_frame = row[9] if "top_frame_site_key" in columns else ""
        same_site = row[10] if "samesite" in columns else -1
        if top_frame or domain not in (host_key or ""):
            continue
        value = _decrypt_cookie_value(encrypted_value, key) or plain_value
        if not name or value is None:
            continue
        cookies.append(
            _to_storage_cookie(
                host_key=host_key,
                name=name,
                value=value,
                path=path or "/",
                expires_utc=expires_utc,
                has_expires=bool(has_expires),
                secure=bool(is_secure),
                http_only=bool(is_httponly),
                same_site=same_site,
            )
        )
    return cookies


def _decrypt_cookie_value(encrypted: bytes, key: bytes) -> str | None:
    if not encrypted:
        return None
    if not encrypted.startswith(b"v10"):
        return encrypted.decode("utf-8", errors="replace")
    nonce, ciphertext = encrypted[3:15], encrypted[15:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return None


def _to_storage_cookie(
    *,
    host_key: str,
    name: str,
    value: str,
    path: str,
    expires_utc: int,
    has_expires: bool,
    secure: bool,
    http_only: bool,
    same_site: int,
) -> dict[str, Any]:
    expires = -1.0
    if has_expires and expires_utc > 0:
        expires = max(-1.0, expires_utc / 1_000_000 - _CHROME_EPOCH_OFFSET)
    cookie: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": host_key,
        "path": path,
        "expires": expires,
        "httpOnly": http_only,
        "secure": secure,
    }
    site = _SAME_SITE_MAP.get(same_site)
    if site:
        cookie["sameSite"] = site
    return cookie

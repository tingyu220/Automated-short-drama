"""Automation Worker 单浏览器、单上下文、单页面运行时。"""
from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

_PLATFORMS = ("tomato", "delivery")

# 每个平台对应的 Cookie 域名关键字（用于保存时分流）
_PLATFORM_DOMAIN_KEYWORDS = {
    "tomato": ("changdupingtai", "douyin", "jinritemai"),
    "delivery": ("tjhaozew",),
}

_BROWSER_STABLE_ARGS = (
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-extensions",
    "--disable-default-apps",
    "--no-first-run",
    "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter,DialMediaRouteProvider",
    "--mute-audio",
    "--blink-settings=imagesEnabled=true",
    "--ignore-certificate-errors",
)


class WorkerBrowserSession:
    """真实 Worker 复用的 Playwright 单页面会话。"""

    def __init__(self, sessions_dir: Path, playwright_factory=None) -> None:
        self._sessions_dir = sessions_dir
        self._playwright_factory = playwright_factory
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._storage_mtimes: dict[str, float] = {}

    def start(self):
        if self._page is not None:
            if self.is_alive():
                return self._page
            self.close()
        factory = self._playwright_factory
        if factory is None:
            from playwright.sync_api import sync_playwright

            factory = sync_playwright
        self._playwright = factory().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=list(_BROWSER_STABLE_ARGS),
        )
        self._context = self._browser.new_context(
            storage_state=load_worker_storage_state(self._sessions_dir),
            ignore_https_errors=True,
            permissions=["clipboard-read", "clipboard-write"],
        )
        self._page = self._context.new_page()
        self._storage_mtimes = self._capture_storage_mtimes()
        return self._page

    def storage_changed_on_disk(self) -> bool:
        """检查磁盘上的 storage.json 是否比浏览器创建时更新（用户重新登录了）。"""
        if not self._storage_mtimes:
            return False
        current = self._capture_storage_mtimes()
        return any(
            current.get(path, 0) > mtime
            for path, mtime in self._storage_mtimes.items()
        )

    def reload_from_disk(self):
        """关闭当前浏览器，用磁盘最新 cookie 重新创建上下文。"""
        was_alive = self._page is not None
        self.close()
        return self.start()

    def _capture_storage_mtimes(self) -> dict[str, float]:
        """记录各平台 storage.json 的修改时间。"""
        mtimes: dict[str, float] = {}
        for platform in _PLATFORMS:
            path = self._sessions_dir / platform / "storage.json"
            if path.exists():
                mtimes[str(path)] = path.stat().st_mtime
        return mtimes

    def is_alive(self) -> bool:
        """判断浏览器、上下文和页面是否仍可用。"""
        if self._page is None or self._context is None or self._browser is None:
            return False
        try:
            page_is_closed = getattr(self._page, "is_closed", None)
            if callable(page_is_closed) and page_is_closed():
                return False
            browser_is_connected = getattr(self._browser, "is_connected", None)
            if callable(browser_is_connected) and not browser_is_connected():
                return False
        except Exception:
            # Playwright 在窗口被外部关闭后查询状态本身也可能抛 TargetClosedError。
            return False
        return True

    def save_storage_state(self) -> None:
        """将当前浏览器上下文的 Cookie / localStorage 按平台分流持久化。

        Worker 运行过程中 Cookie 会被服务端刷新（如会话续期），
        如果不写回磁盘，下次重启就会加载过期 Cookie 导致登录失效。
        """
        if self._context is None:
            return
        try:
            state = self._context.storage_state()
        except Exception as exc:
            logger = _get_logger()
            logger.warning("保存 Worker storage_state 失败: %s", exc)
            return

        cookies = state.get("cookies") or []
        origins = state.get("origins") or []

        # 按域名关键字分流到各平台
        platform_cookies: dict[str, list[dict]] = {p: [] for p in _PLATFORMS}
        for cookie in cookies:
            domain = str(cookie.get("domain", ""))
            for platform, keywords in _PLATFORM_DOMAIN_KEYWORDS.items():
                if any(kw in domain for kw in keywords):
                    platform_cookies[platform].append(cookie)
                    break
            else:
                # 未匹配到平台的 Cookie 也保留（避免丢失）
                for p in _PLATFORMS:
                    platform_cookies[p].append(cookie)

        # 按平台写回 storage.json，与现有 Cookie 合并去重
        for platform in _PLATFORMS:
            path = self._sessions_dir / platform / "storage.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            existing_cookies: list[dict] = []
            existing_origins: list[dict] = []
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(existing, dict):
                        existing_cookies = existing.get("cookies") or []
                        existing_origins = existing.get("origins") or []
                except (OSError, json.JSONDecodeError):
                    pass
            merged_cookies = _dedupe_cookies(
                platform_cookies[platform] + existing_cookies
            )
            payload = {
                "cookies": merged_cookies,
                "origins": existing_origins + origins,
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def close(self) -> None:
        # 关闭前先保存登录态，确保 Cookie 续期后写回磁盘
        try:
            self.save_storage_state()
        except Exception:
            pass
        for resource, method_name in (
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ):
            if resource is None:
                continue
            try:
                getattr(resource, method_name)()
            except Exception:
                # 外部关闭窗口后资源已失效，清理必须保持幂等。
                pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None


def load_worker_storage_state(sessions_dir: Path) -> dict:
    """加载 Worker 所需平台的合并登录态。"""
    cookies: list[dict] = []
    origins: list[dict] = []
    cookie_keys: set[tuple[str, str, str]] = set()
    origin_keys: set[str] = set()
    for platform in _PLATFORMS:
        path = sessions_dir / platform / "storage.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"登录态文件损坏: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"登录态文件损坏: {path}")
        for cookie in payload.get("cookies") or []:
            sanitized = _sanitize_cookie(cookie)
            if sanitized is None:
                continue
            key = (
                sanitized["name"],
                sanitized["domain"],
                sanitized["path"],
            )
            if key not in cookie_keys:
                cookie_keys.add(key)
                cookies.append(sanitized)
        for origin in payload.get("origins") or []:
            key = str(origin.get("origin") or "")
            if key and key not in origin_keys:
                origin_keys.add(key)
                origins.append(origin)
    return {"cookies": cookies, "origins": origins}


def _dedupe_cookies(cookies: list[dict]) -> list[dict]:
    """按 (name, domain, path) 去重，后面的 Cookie 覆盖前面的（优先保留新值）。"""
    seen: dict[tuple[str, str, str], dict] = {}
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        domain = cookie.get("domain")
        path = cookie.get("path") or "/"
        if not name or not domain:
            continue
        key = (name, domain, path)
        seen[key] = cookie
    return list(seen.values())


def _get_logger():
    """延迟获取 logger，避免模块导入时的循环依赖。"""
    import logging

    return logging.getLogger(__name__)


_VALID_SAMESITE = {"Strict", "Lax", "None"}


def _sanitize_cookie(cookie: dict) -> dict | None:
    """清洗单个 cookie 字典，返回 Playwright 兼容格式。

    返回 None 表示该 cookie 字段缺失无法使用。
    """
    if not isinstance(cookie, dict):
        return None
    name = cookie.get("name")
    value = cookie.get("value")
    domain = cookie.get("domain")
    path = cookie.get("path")
    if not name or not isinstance(name, str):
        return None
    if value is None or not isinstance(value, str):
        return None
    if not domain or not isinstance(domain, str):
        return None
    if not path or not isinstance(path, str):
        path = "/"
    result: dict = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
    }
    expires = cookie.get("expires")
    if expires is None:
        result["expires"] = -1.0
    elif isinstance(expires, (int, float)):
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
    return result


def cleanup_zombie_browsers(sessions_dir: Path | None = None) -> int:
    """清理上一次 Worker 崩溃后遗漏的 Playwright 浏览器进程。

    只清理命令行中含有 Playwright 特征参数的 Chrome/Chromium 进程，
    不误伤用户正常使用的浏览器。

    Returns:
        杀掉的进程数。
    """
    system = platform.system()
    if system == "Windows":
        return _cleanup_zombie_windows()
    if system in ("Linux", "Darwin"):
        return _cleanup_zombie_posix(system)
    return 0


def _cleanup_zombie_windows() -> int:
    """Windows 下通过 PowerShell 查找并杀掉 Playwright 启动的 Chrome 进程。

    使用 PowerShell CIM 代替 wmi 模块，避免 WMI 枚举无超时导致 Worker 卡死。
    """
    killed = 0
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -match 'chrome' -and "
                "$_.CommandLine -match '--remote-debugging-port' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                "-ErrorAction SilentlyContinue; 'killed' }",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        killed = len(
            [line for line in result.stdout.splitlines() if line.strip() == "killed"]
        )
    except Exception:
        pass
    return killed


def _cleanup_zombie_windows_fallback() -> int:
    """不依赖 wmi 的 Windows 清理实现。"""
    killed = 0
    try:
        result = subprocess.run(
            ["wmic", "process", "get", "processid,commandline,name", "/format:csv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if not line.strip() or line.startswith("Node,"):
                continue
            parts = line.split(",")
            if len(parts) < 4:
                continue
            # CSV 格式: Node,CommandLine,Name,ProcessId
            name = parts[2].lower() if len(parts) > 2 else ""
            if name not in ("chrome.exe", "chrome-headless-shell.exe"):
                continue
            cmd = parts[1] if len(parts) > 1 else ""
            try:
                pid = int(parts[-1])
            except (ValueError, IndexError):
                continue
            if _is_playwright_chrome_cmd(cmd):
                try:
                    os.kill(pid, 9)
                    killed += 1
                except (OSError, ProcessLookupError):
                    pass
    except Exception:
        pass
    return killed


def _cleanup_zombie_posix(system: str) -> int:
    """Linux/macOS 下通过 ps 查找并杀掉 Playwright 启动的 Chrome 进程。"""
    killed = 0
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,args="],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            pid_str, comm, args = parts[0], parts[1], parts[2]
            comm_lower = comm.lower()
            if "chrome" not in comm_lower and "chromium" not in comm_lower:
                continue
            if not _is_playwright_chrome_cmd(args):
                continue
            try:
                pid = int(pid_str)
                os.kill(pid, 9)
                killed += 1
            except (OSError, ValueError, ProcessLookupError):
                pass
    except Exception:
        pass
    return killed


def _is_playwright_chrome_cmd(cmd: str) -> bool:
    """判断命令行是否为 Playwright 启动的浏览器（特征：headless + remote-debugging-port）。"""
    if not cmd:
        return False
    has_headless = "--headless" in cmd or "--headless=new" in cmd
    has_debug_port = "--remote-debugging-port" in cmd
    # Playwright 会同时带这两个参数
    return has_headless and has_debug_port

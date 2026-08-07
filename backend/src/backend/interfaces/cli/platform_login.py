"""平台登录 CLI：手动登录并持久化浏览器 Session。

用法:
    python -m backend.interfaces.cli.platform_login login tomato [--auto-save]
    python -m backend.interfaces.cli.platform_login check feishu
    python -m backend.interfaces.cli.platform_login import tomato storage.json
    python -m backend.interfaces.cli.platform_login clear ocean

番茄登录复用畅读首页弹窗流程：登录成功后检测到漫剧/短剧菜单即自动保存。
账号密码可选环境变量：WORKBUDDY_CHANGDU_ACCOUNT / WORKBUDDY_CHANGDU_PASSWORD。
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from backend.application.services.session_service import (
    PLATFORM_LOGIN_URLS,
    SessionService,
)
from backend.infrastructure.config.settings import Settings

_TOMATO_HOME_URL = "https://www.changdupingtai.com/page/home?show=true"
_TOMATO_LOGGED_IN_SELECTORS = (
    ".layout-menus-cascader",
    ".arco-cascader-view",
    "a[href*='/sale/short-play/list']",
    "a[href*='/sale/novel/list']",
)
_LOGIN_WAIT_SECONDS = 600


def _profile_dir(platform: str) -> Path:
    return Settings().data_dir / "sessions" / platform / "profile"


def _login(platform: str, auto_save: bool) -> int:
    """打开持久化浏览器完成登录，保存 storage_state。"""
    if platform not in PLATFORM_LOGIN_URLS or platform == "feishu":
        print(f"平台 {platform} 不支持网页手动登录")
        return 2
    from playwright.sync_api import sync_playwright

    user_data_dir = _profile_dir(platform)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )
        ok = (
            _login_tomato(context, auto_save)
            if platform == "tomato"
            else _login_generic(platform, context, auto_save)
        )
        context.close()
        return 0 if ok else 2


def _login_tomato(context, auto_save: bool) -> bool:
    """番茄登录：首页弹窗 + 可选自动填账号 + 验证码人工完成。"""
    page = context.new_page()
    page.goto(_TOMATO_HOME_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2000)
    if _tomato_logged_in(page):
        _save_storage(context, "tomato")
        return True

    login_btn = page.locator("span").filter(has_text="登录").first
    if login_btn.count():
        login_btn.click()
        page.wait_for_timeout(2000)

    _fill_tomato_credentials(page)
    deadline = time.time() + _LOGIN_WAIT_SECONDS
    while time.time() < deadline:
        if _tomato_logged_in(page):
            _save_storage(context, "tomato")
            return True
        if not auto_save:
            input("登录完成后按回车保存登录态...")
            _save_storage(context, "tomato")
            return True
        time.sleep(2)

    print("等待番茄登录超时（10 分钟），未保存登录态")
    return False


def _fill_tomato_credentials(page) -> None:
    """环境变量存在时自动填写畅读账号密码。"""
    account = os.getenv("WORKBUDDY_CHANGDU_ACCOUNT", "").strip()
    password = os.getenv("WORKBUDDY_CHANGDU_PASSWORD", "").strip()
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
    """判断畅读是否已进入登录后菜单（与历史脚本一致）。"""
    for selector in _TOMATO_LOGGED_IN_SELECTORS:
        if page.query_selector(selector):
            return True
    return False


def _login_generic(platform: str, context, auto_save: bool) -> bool:
    """投放/巨量通用登录：URL 离开登录页或新增 Cookie 即保存。"""
    page = context.new_page()
    page.goto(PLATFORM_LOGIN_URLS[platform], wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    initial_keys = _cookie_keys(context)
    deadline = time.time() + _LOGIN_WAIT_SECONDS
    while time.time() < deadline:
        current_keys = _cookie_keys(context)
        url = page.url.lower()
        if current_keys - initial_keys or (
            url and "login" not in url and "login" in PLATFORM_LOGIN_URLS[platform]
        ):
            _save_storage(context, platform)
            return True
        if not auto_save:
            input("登录完成后按回车保存登录态...")
            _save_storage(context, platform)
            return True
        time.sleep(2)
    print(f"等待 {platform} 登录超时（10 分钟），未保存登录态")
    return False


def _cookie_keys(context) -> set[tuple[str, str]]:
    return {
        (cookie["name"], cookie.get("domain", ""))
        for cookie in context.cookies()
    }


def _save_storage(context, platform: str) -> None:
    """导出 storage_state 到项目 Session 目录。"""
    storage_path = Settings().data_dir / "sessions" / platform / "storage.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(storage_path))
    print(f"登录态已保存：{storage_path}")


def _import_storage(platform: str, storage_file: str) -> int:
    """从 storage_state JSON 文件导入登录态。"""
    try:
        data = json.loads(Path(storage_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取 storage 文件失败: {exc}")
        return 2
    if not isinstance(data, dict):
        print("storage 文件必须是 JSON 对象")
        return 2
    path = SessionService().import_storage(platform, data)
    print(f"已导入登录态：{path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """解析命令并执行。"""
    parser = argparse.ArgumentParser(description="平台登录态管理")
    sub = parser.add_subparsers(dest="command", required=True)

    login_parser = sub.add_parser("login", help="打开浏览器手动登录")
    login_parser.add_argument("platform", choices=sorted(PLATFORM_LOGIN_URLS))
    login_parser.add_argument(
        "--auto-save",
        action="store_true",
        default=False,
        help="检测到登录成功后自动保存",
    )

    check_parser = sub.add_parser("check", help="检查登录态")
    check_parser.add_argument("platform", choices=sorted(PLATFORM_LOGIN_URLS))

    import_parser = sub.add_parser("import", help="导入 storage_state JSON")
    import_parser.add_argument("platform", choices=sorted(PLATFORM_LOGIN_URLS))
    import_parser.add_argument("storage_file")

    clear_parser = sub.add_parser("clear", help="清除本地登录态")
    clear_parser.add_argument("platform", choices=sorted(PLATFORM_LOGIN_URLS))

    args = parser.parse_args(argv)
    if args.command == "login":
        return _login(args.platform, args.auto_save)
    if args.command == "check":
        print(
            json.dumps(
                SessionService().check(args.platform).__dict__,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "import":
        return _import_storage(args.platform, args.storage_file)
    if args.command == "clear":
        SessionService().clear(args.platform)
        print(f"已清除 {args.platform} 登录态")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

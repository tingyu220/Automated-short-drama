"""平台登录 CLI：手动登录并持久化浏览器 Session。

用法:
    python -m backend.interfaces.cli.platform_login login tomato
    python -m backend.interfaces.cli.platform_login check feishu
    python -m backend.interfaces.cli.platform_login import tomato storage.json
    python -m backend.interfaces.cli.platform_login clear ocean
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from backend.application.services.session_service import (
    PLATFORM_LOGIN_URLS,
    SessionService,
)
from backend.infrastructure.config.settings import Settings


def _profile_dir(platform: str) -> Path:
    return Settings().data_dir / "sessions" / platform / "profile"


def _login(platform: str, auto_save: bool) -> int:
    """打开持久化浏览器完成手动登录，保存 storage_state。"""
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
        )
        page = context.new_page()
        page.goto(PLATFORM_LOGIN_URLS[platform])
        if auto_save:
            print(
                "请在打开的浏览器中登录，检测到离开登录页后自动保存..."
            )
            deadline = time.time() + 600
            saved = False
            while time.time() < deadline:
                current = page.url.lower()
                if current and "login" not in current:
                    _save_storage(context, platform)
                    saved = True
                    break
                time.sleep(2)
            context.close()
            if not saved:
                print("等待登录超时（10 分钟），未保存登录态")
                return 2
        else:
            print(f"请在打开的浏览器中登录：{PLATFORM_LOGIN_URLS[platform]}")
            input("登录完成后按回车保存登录态...")
            _save_storage(context, platform)
            context.close()
    return 0


def _save_storage(context, platform: str) -> None:
    """导出持久化 context 的 storage_state 到项目 Session 目录。"""
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
        help="检测到离开登录页后自动保存",
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
        print(json.dumps(SessionService().check(args.platform).__dict__, ensure_ascii=False, indent=2))
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

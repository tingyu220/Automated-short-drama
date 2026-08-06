"""Control Server 启动入口。

用法: python -m backend.bootstrap.control_server [--host HOST] [--port PORT] [--reload] [--skip-seed]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.infrastructure.config.settings import Settings
from backend.infrastructure.database.migrations import run_migrations
from backend.infrastructure.database.session import SessionLocal


def _seed_defaults(defaults_path: Path | None) -> None:
    """导入默认规则配置，失败则中止启动。"""
    path = defaults_path or (Settings().config_defaults_dir / "rules.json")
    session = SessionLocal()
    try:
        result = seed_rules_from_defaults(session, path)
        session.commit()
        print(
            f"默认规则初始化完成: "
            f"created={result.created_rules}, skipped={result.skipped_rules}"
        )
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并启动 uvicorn。

    Returns:
        退出码（0 成功，非 0 失败）。
    """
    parser = argparse.ArgumentParser(description="短剧投放全流程自动化工作台 - Control Server")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="绑定端口（默认 8765）")
    parser.add_argument("--reload", action="store_true", default=False, help="开启热重载")
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        default=False,
        help="跳过数据库迁移",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        default=False,
        help="跳过默认规则初始化导入",
    )
    parser.add_argument(
        "--defaults-path",
        type=Path,
        default=None,
        help="默认规则 JSON 路径（默认 configs/defaults/rules.json）",
    )
    args = parser.parse_args(argv)

    # 启动前自动执行数据库迁移
    if not args.skip_migrations:
        run_migrations()

    if not args.skip_seed:
        _seed_defaults(args.defaults_path)

    uvicorn.run(
        "backend.interfaces.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

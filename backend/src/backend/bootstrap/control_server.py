"""Control Server 启动入口。

用法: python -m backend.bootstrap.control_server [--host HOST] [--port PORT] [--reload]
"""
from __future__ import annotations

import argparse

import uvicorn


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并启动 uvicorn。

    Returns:
        退出码（0 成功，非 0 失败）。
    """
    parser = argparse.ArgumentParser(description="短剧投放全流程自动化工作台 - Control Server")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="绑定端口（默认 8765）")
    parser.add_argument("--reload", action="store_true", default=False, help="开启热重载")
    args = parser.parse_args(argv)

    uvicorn.run(
        "backend.interfaces.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

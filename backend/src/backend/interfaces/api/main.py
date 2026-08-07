"""FastAPI 应用工厂，挂载路由与异常处理器。"""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.domain.errors.domain_error import DomainError
from backend.interfaces.api.errors import to_http_error
from backend.interfaces.api.routes.accounts import router as accounts_router
from backend.interfaces.api.routes.delivery_config import (
    router as delivery_config_router,
)
from backend.interfaces.api.routes.exceptions import router as exceptions_router
from backend.interfaces.api.routes.health import router as health_router
from backend.interfaces.api.routes.queue import router as queue_router
from backend.interfaces.api.routes.records import router as records_router
from backend.interfaces.api.routes.rules import router as rules_router
from backend.interfaces.api.routes.sessions import router as sessions_router
from backend.interfaces.api.routes.tasks import router as tasks_router


def create_app(dist_dir: Path | None = None) -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(title="短剧投放全流程自动化工作台")

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        http_exc = to_http_error(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    app.include_router(health_router)
    app.include_router(tasks_router, prefix="/api")
    app.include_router(queue_router, prefix="/api")
    app.include_router(rules_router, prefix="/api")
    app.include_router(records_router, prefix="/api")
    app.include_router(accounts_router, prefix="/api")
    app.include_router(delivery_config_router, prefix="/api")
    app.include_router(exceptions_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")

    # 生产环境自动检测 dashboard/dist；测试可传 dist_dir 覆盖
    _dist = dist_dir if dist_dir is not None else _resolve_default_dist_dir()
    mount_frontend(app, _dist)

    return app


def mount_frontend(app: FastAPI, dist_dir: Path | None) -> None:
    """如果 dist_dir 存在且为目录，挂载前端静态文件到 /。"""
    if dist_dir is None:
        return
    if not dist_dir.is_dir():
        return
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")


def _resolve_default_dist_dir() -> Path | None:
    """基于 main.py 位置推算项目根目录下的 dashboard/dist。"""
    _project_root = Path(__file__).resolve().parents[5]
    _candidate = _project_root / "dashboard" / "dist"
    return _candidate if _candidate.is_dir() else None


app = create_app()

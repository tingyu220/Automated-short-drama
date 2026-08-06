"""FastAPI 应用工厂，挂载路由与异常处理器。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse

from backend.domain.errors.domain_error import DomainError
from backend.interfaces.api.errors import to_http_error
from backend.interfaces.api.routes.health import router as health_router


def create_app() -> FastAPI:
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
    return app


app = create_app()

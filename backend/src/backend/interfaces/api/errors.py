"""将 DomainError 转换为 FastAPI HTTPException。"""
from __future__ import annotations

from fastapi import HTTPException

from backend.domain.errors.domain_error import (
    ConfigurationError,
    ConflictError,
    DomainError,
    ExternalAdapterError,
    NotFoundError,
    ValidationError,
)

_STATUS_MAP: dict[type[DomainError], int] = {
    ConfigurationError: 400,
    ValidationError: 400,
    NotFoundError: 404,
    ConflictError: 409,
    ExternalAdapterError: 502,
}


def to_http_error(exc: DomainError) -> HTTPException:
    """将领域错误映射为 HTTPException，detail 仅含 code 与 message。"""
    status_code = _STATUS_MAP.get(type(exc), 500)
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )

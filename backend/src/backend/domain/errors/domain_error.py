"""领域层统一错误模型。"""
from __future__ import annotations


class DomainError(Exception):
    """领域错误基类。"""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "DOMAIN_ERROR",
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code!r}, "
            f"message={self.message!r})"
        )


class ConfigurationError(DomainError):
    """配置错误。"""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, code="CONFIGURATION_ERROR", **kwargs)  # type: ignore[arg-type]


class NotFoundError(DomainError):
    """资源未找到。"""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, code="NOT_FOUND", **kwargs)  # type: ignore[arg-type]


class ConflictError(DomainError):
    """资源冲突。"""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, code="CONFLICT", **kwargs)  # type: ignore[arg-type]


class ExternalAdapterError(DomainError):
    """外部适配器错误。"""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "EXTERNAL_ADAPTER_ERROR",
        **kwargs: object,
    ) -> None:
        super().__init__(message, code=code, **kwargs)  # type: ignore[arg-type]


class DramaMismatchError(DomainError):
    """剧名与分钟级发布时间无法唯一匹配。"""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, code="DRAMA_MISMATCH", **kwargs)  # type: ignore[arg-type]


class ValidationError(DomainError):
    """校验错误。"""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, code="VALIDATION_ERROR", **kwargs)  # type: ignore[arg-type]

"""领域错误与 HTTP 转换测试。"""
from __future__ import annotations

import pytest

from backend.domain.errors.domain_error import (
    ConfigurationError,
    ConflictError,
    DomainError,
    ExternalAdapterError,
    NotFoundError,
    ValidationError,
)
from backend.interfaces.api.errors import to_http_error


class TestDomainErrorSubclasses:
    """各子类 code / message 测试。"""

    def test_domain_error_defaults(self):
        err = DomainError()
        assert err.code == "DOMAIN_ERROR"
        assert err.message == ""
        assert err.details == {}

    def test_configuration_error(self):
        err = ConfigurationError("配置缺失")
        assert err.code == "CONFIGURATION_ERROR"
        assert err.message == "配置缺失"

    def test_not_found_error(self):
        err = NotFoundError("用户未找到", details={"user_id": 1})
        assert err.code == "NOT_FOUND"
        assert err.message == "用户未找到"
        assert err.details == {"user_id": 1}

    def test_conflict_error(self):
        err = ConflictError("名称冲突")
        assert err.code == "CONFLICT"

    def test_external_adapter_error(self):
        err = ExternalAdapterError("API 超时")
        assert err.code == "EXTERNAL_ADAPTER_ERROR"

    def test_validation_error(self):
        err = ValidationError("字段必填")
        assert err.code == "VALIDATION_ERROR"


class TestToHttpError:
    """to_http_error 状态码映射测试。"""

    @pytest.mark.parametrize("exc_class,expected_status", [
        (ConfigurationError, 400),
        (ValidationError, 400),
        (NotFoundError, 404),
        (ConflictError, 409),
        (ExternalAdapterError, 502),
    ])
    def test_status_code_mapping(self, exc_class, expected_status):
        http_exc = to_http_error(exc_class("test"))
        assert http_exc.status_code == expected_status
        assert "code" in http_exc.detail
        assert "message" in http_exc.detail

    def test_unknown_domain_error_falls_back_to_500(self):
        class CustomError(DomainError):
            pass
        http_exc = to_http_error(CustomError("未知错误"))
        assert http_exc.status_code == 500

    def test_detail_does_not_leak_stack(self):
        """detail 只包含 code 和 message，不泄露堆栈。"""
        try:
            raise ConfigurationError("敏感配置")
        except ConfigurationError as exc:
            http_exc = to_http_error(exc)
        detail = http_exc.detail
        assert set(detail.keys()) == {"code", "message"}
        assert "stack" not in str(detail).lower()

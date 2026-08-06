"""Logger 日志模块测试。"""
from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from backend.infrastructure.logging.logger import get_logger


class TestSanitization:
    """敏感字段脱敏测试。"""

    @pytest.fixture(autouse=True)
    def _clear_handlers(self):
        """每个测试前重置 handler 状态。"""
        import backend.infrastructure.logging.logger as mod
        mod._HANDLER_INSTALLED = False

    def test_password_is_masked(self):
        """包含 password 键的值应被替换为 ***。"""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        from backend.infrastructure.logging.logger import _SanitizingFormatter
        handler.setFormatter(_SanitizingFormatter())

        logger = logging.getLogger("test_password")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.propagate = False

        logger.info("login", extra={"user": "admin", "password": "secret123"})
        record = json.loads(stream.getvalue().strip())
        assert record["password"] == "***"

    def test_token_is_masked(self):
        """包含 token 键的值应被替换为 ***。"""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        from backend.infrastructure.logging.logger import _SanitizingFormatter
        handler.setFormatter(_SanitizingFormatter())

        logger = logging.getLogger("test_token")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.propagate = False

        logger.info("request", extra={"auth_token": "abc123xyz"})
        record = json.loads(stream.getvalue().strip())
        assert record["auth_token"] == "***"


class TestIdempotent:
    """get_logger 幂等性测试。"""

    @pytest.fixture(autouse=True)
    def _clear_handlers(self):
        """每个测试前重置 handler 状态。"""
        import backend.infrastructure.logging.logger as mod
        mod._HANDLER_INSTALLED = False

    def test_repeated_calls_no_dup_handlers(self):
        """多次调用 get_logger 不会重复添加 handler。"""
        logger1 = get_logger("test_idempotent")
        logger2 = get_logger("test_idempotent")
        assert logger1 is logger2
        handlers_before = len(logger1.handlers)
        get_logger("another")
        assert len(logger1.handlers) == handlers_before

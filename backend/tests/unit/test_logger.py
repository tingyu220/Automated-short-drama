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
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

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
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_repeated_calls_no_dup_handlers(self):
        """多次调用 get_logger 不会重复添加 handler。"""
        get_logger("test_idempotent_a")
        root = logging.getLogger()
        handlers_after_first = len(root.handlers)
        get_logger("test_idempotent_b")
        assert len(root.handlers) == handlers_after_first


class TestEndToEnd:
    """端到端测试：两个不相关的 logger 都能输出。"""

    @pytest.fixture(autouse=True)
    def _clear_handlers(self):
        """每个测试前重置 handler 状态。"""
        import backend.infrastructure.logging.logger as mod
        mod._HANDLER_INSTALLED = False
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_two_unrelated_loggers_both_output(self):
        """module.a 和 module.b 两个不相关的 logger 都能通过根 handler 输出。"""
        stream = StringIO()
        import backend.infrastructure.logging.logger as mod
        mod._HANDLER_INSTALLED = False

        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        from backend.infrastructure.logging.logger import _SanitizingFormatter
        handler.setFormatter(_SanitizingFormatter())
        root.addHandler(handler)

        log_a = get_logger("module.a")
        log_b = get_logger("module.b")
        log_a.info("消息 A")
        log_b.info("消息 B")

        lines = stream.getvalue().strip().split("\n")
        records = [json.loads(line) for line in lines]
        loggers = {r["logger"] for r in records}
        assert "module.a" in loggers
        assert "module.b" in loggers
        assert len(records) == 2

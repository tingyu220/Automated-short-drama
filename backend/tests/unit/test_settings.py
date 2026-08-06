"""Settings 配置加载测试。"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestAllowFinalSubmit:
    """allow_final_submit 严格布尔解析。"""

    def test_default_is_false(self):
        """默认值为 False。"""
        from backend.infrastructure.config.settings import Settings
        s = Settings()
        assert s.allow_final_submit is False

    @pytest.mark.parametrize("raw,expected", [
        ("true", True),
        ("false", False),
        ("TRUE", True),
        ("FALSE", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        ("on", True),
        ("off", False),
        (True, True),
        (False, False),
    ])
    def test_valid_bool_strings(self, raw, expected):
        """合法的布尔表示应正确解析。"""
        from backend.infrastructure.config.settings import Settings
        with patch.dict(os.environ, {"WORKBUDDY_ALLOW_FINAL_SUBMIT": str(raw)}, clear=True):
            s = Settings()
        assert s.allow_final_submit is expected

    def test_invalid_bool_raises(self):
        """非法布尔值导致校验失败。"""
        from backend.infrastructure.config.settings import Settings
        from pydantic import ValidationError
        with patch.dict(os.environ, {"WORKBUDDY_ALLOW_FINAL_SUBMIT": "maybe"}, clear=True):
            with pytest.raises(ValidationError):
                Settings()


class TestDefaults:
    """host / port 默认值。"""

    def test_host_default(self):
        from backend.infrastructure.config.settings import Settings
        s = Settings()
        assert s.host == "127.0.0.1"

    def test_port_default(self):
        from backend.infrastructure.config.settings import Settings
        s = Settings()
        assert s.port == 8765

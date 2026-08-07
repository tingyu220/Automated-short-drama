"""SessionLoginManager 基础行为测试（不启动真实 Playwright）。"""
from __future__ import annotations

import pytest

from backend.application.services.session_login import SessionLoginManager


def test_finish_without_running_returns_false(tmp_path):
    manager = SessionLoginManager(sessions_dir=tmp_path)

    assert manager.is_running("tomato") is False
    assert manager.finish("tomato") is False


def test_start_unsupported_platform_raises(tmp_path):
    manager = SessionLoginManager(sessions_dir=tmp_path)

    with pytest.raises(ValueError):
        manager.start("feishu")


def test_storage_path_under_sessions_dir(tmp_path):
    manager = SessionLoginManager(sessions_dir=tmp_path)

    assert manager.storage_path("tomato") == (
        tmp_path / "tomato" / "storage.json"
    )

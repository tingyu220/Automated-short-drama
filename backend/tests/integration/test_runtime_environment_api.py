"""运行环境 API 集成测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.infrastructure.database.engine import create_app_engine
from backend.infrastructure.config.settings import Settings
from backend.interfaces.api.main import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    """使用迁移后的临时数据库创建 API 客户端。"""
    monkeypatch.setenv("WORKBUDDY_FEISHU_TASK_SHEET_URL", "https://example.test/sheet")
    db_url = f"sqlite:///{tmp_path / 'runtime_environment.db'}"
    engine = create_app_engine(db_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(Path("alembic").resolve()))
    command.upgrade(cfg, "head")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(
        "backend.infrastructure.database.session.SessionLocal", factory
    )
    app = create_app(dist_dir=None)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


def test_runtime_environment_defaults_to_mock_and_requires_confirmation_for_real(
    client,
) -> None:
    """真实环境必须显式确认，默认保持模拟环境。"""
    assert client.get("/api/runtime/environment").json() == {
        "desired_mode": "MOCK",
        "worker_mode": None,
        "switching": False,
        "operator_match_group": False,
    }

    rejected = client.put(
        "/api/runtime/environment", json={"mode": "REAL", "confirm_real": False}
    )
    assert rejected.status_code == 422

    accepted = client.put(
        "/api/runtime/environment", json={"mode": "REAL", "confirm_real": True}
    )
    assert accepted.status_code == 200
    assert accepted.json() == {
        "desired_mode": "REAL",
        "worker_mode": None,
        "switching": True,
        "operator_match_group": False,
    }


def test_real_environment_uses_feishu_url_loaded_by_settings(client, monkeypatch) -> None:
    """切换校验必须认可 Settings 从 .env 读取到的飞书剧目表。"""
    monkeypatch.delenv("WORKBUDDY_FEISHU_TASK_SHEET_URL", raising=False)
    monkeypatch.setattr(
        "backend.interfaces.api.routes.runtime.Settings",
        lambda: Settings(feishu_task_sheet_url="https://example.test/from-settings"),
    )

    response = client.put(
        "/api/runtime/environment", json={"mode": "REAL", "confirm_real": True}
    )

    assert response.status_code == 200


def test_operator_match_group_can_be_toggled(client) -> None:
    """前端可通过 API 切换剧目匹配范围。"""
    turned_on = client.put(
        "/api/runtime/operator-match", json={"match_group": True}
    )
    assert turned_on.status_code == 200
    assert turned_on.json()["operator_match_group"] is True

    turned_off = client.put(
        "/api/runtime/operator-match", json={"match_group": False}
    )
    assert turned_off.status_code == 200
    assert turned_off.json()["operator_match_group"] is False

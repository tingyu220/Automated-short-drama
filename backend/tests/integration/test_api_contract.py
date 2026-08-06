"""前后端联调 API 契约测试 —— 临时 SQLite + Alembic + 默认规则 seed。"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.application.services.rule_seed_service import seed_rules_from_defaults
from backend.domain.rules.rule_version import RuleVersionStatus
from backend.infrastructure.config.settings import PROJECT_ROOT
from backend.infrastructure.database.engine import create_app_engine
from backend.interfaces.api.main import create_app

DEFAULTS_PATH = PROJECT_ROOT / "configs" / "defaults" / "rules.json"


@pytest.fixture
def client(monkeypatch, tmp_path):
    """迁移+seed 临时数据库后创建 TestClient。"""
    db_url = f"sqlite:///{tmp_path / 'contract.db'}"
    engine = create_app_engine(db_url)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(Path("alembic").resolve()))
    command.upgrade(alembic_cfg, "head")

    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    with session_factory() as session:
        seed_rules_from_defaults(session, DEFAULTS_PATH)
        session.commit()
    monkeypatch.setattr(
        "backend.infrastructure.database.session.SessionLocal", session_factory
    )
    app = create_app(dist_dir=None)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


class TestApiContract:
    """Phase 5 前后端联调 API 契约检查。"""

    def test_healthz_returns_200(self, client):
        """健康检查返回 200。"""
        response = client.get("/healthz")
        assert response.status_code == 200

    def test_core_read_endpoints_return_200_json(self, client):
        """核心页面依赖 API 均 200 且响应为 JSON 列表/对象。"""
        list_endpoints = [
            "/api/tasks",
            "/api/queue",
            "/api/rules",
            "/api/exceptions",
            "/api/records/ledgers",
        ]
        for path in list_endpoints:
            response = client.get(path)
            assert response.status_code == 200, path
            assert isinstance(response.json(), list), path

        overview = client.get("/api/accounts/overview")
        assert overview.status_code == 200
        assert isinstance(overview.json(), dict)

    def test_rule_publish_versions_contract(self, client):
        """规则发布后 /api/rules/{id}/versions 包含已发布版本。"""
        rule_sets = client.get("/api/rules").json()
        rule_id = next(
            row["id"] for row in rule_sets if row["key"] == "iap_price_2_9"
        )

        published = client.post(f"/api/rules/{rule_id}/publish")
        assert published.status_code == 200
        assert published.json()["status"] == RuleVersionStatus.PUBLISHED

        versions = client.get(f"/api/rules/{rule_id}/versions").json()
        assert any(
            item["status"] == RuleVersionStatus.PUBLISHED for item in versions
        )

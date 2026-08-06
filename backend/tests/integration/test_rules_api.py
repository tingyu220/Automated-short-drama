"""规则 API 集成测试 —— 临时 SQLite + Alembic + 默认规则 seed。"""
from __future__ import annotations

import uuid
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
def session_factory(monkeypatch, tmp_path):
    """创建临时数据库并导入默认规则，全局会话指向它。"""
    db_url = f"sqlite:///{tmp_path / 'rules_api.db'}"
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
    yield session_factory
    engine.dispose()


@pytest.fixture
def client(session_factory):
    """创建测试客户端。"""
    app = create_app(dist_dir=None)
    with TestClient(app) as test_client:
        yield test_client


class TestRulesApi:
    """规则列表、版本、校验、发布与价格模拟 API 测试。"""

    def test_list_rule_sets(self, client):
        """GET /api/rules 返回全部默认规则集视图。"""
        response = client.get("/api/rules")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        keys = {item["key"] for item in data}
        assert keys == {"iaa_episode_threshold", "iap_price_2_9", "iap_price_9_9"}
        item = next(row for row in data if row["key"] == "iap_price_2_9")
        assert {"id", "key", "name", "category", "status", "updated_at"} <= set(item)
        assert item["status"] == "DRAFT"

    def test_versions_validate_publish(self, client):
        """版本列表、校验与发布流程正确。"""
        rule_sets = client.get("/api/rules").json()
        rule_id = next(
            row["id"] for row in rule_sets if row["key"] == "iap_price_2_9"
        )

        versions_before = client.get(f"/api/rules/{rule_id}/versions")
        assert versions_before.status_code == 200
        assert len(versions_before.json()) == 1
        assert versions_before.json()[0]["status"] == RuleVersionStatus.DRAFT

        validated = client.post(f"/api/rules/{rule_id}/validate")
        assert validated.status_code == 200
        validating = validated.json()
        assert validating["status"] == RuleVersionStatus.VALIDATING
        assert validating["published_at"] is None

        published = client.post(f"/api/rules/{rule_id}/publish")
        assert published.status_code == 200
        published_data = published.json()
        assert published_data["status"] == RuleVersionStatus.PUBLISHED
        assert published_data["published_at"] is not None
        assert published_data["version"] == "2"

        versions_after = client.get(f"/api/rules/{rule_id}/versions").json()
        assert len(versions_after) == 2
        assert versions_after[0]["version"] == "2"

    def test_unknown_rule_set_returns_404(self, client):
        """不存在的规则集在版本/校验接口返回 404。"""
        rule_id = str(uuid.uuid4())
        assert client.get(f"/api/rules/{rule_id}/versions").status_code == 404
        assert client.post(f"/api/rules/{rule_id}/validate").status_code == 404
        assert client.post(f"/api/rules/{rule_id}/publish").status_code == 404

    def test_simulate_price(self, client):
        """价格模拟返回 inputs 与逐候选匹配结果。"""
        response = client.post(
            "/api/rules/simulate-price",
            json={"candidates": [2.8, 6.0, 10.0]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["inputs"] == [2.8, 6.0, 10.0]
        assert [output["matched_rule_key"] for output in data["outputs"]] == [
            "iap_2_9",
            None,
            "iap_9_9",
        ]
        assert data["outputs"][0]["distance"] == pytest.approx(0.1)
        assert data["outputs"][1]["selection_reason"] == "NO_MATCH"

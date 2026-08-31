"""账户 API 集成测试 —— 内存 Mock 账户表与分配预览。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.interfaces.api.main import create_app
from backend.interfaces.api.routes import accounts as accounts_route
from backend.domain.rules.account_block import AccountRow


class TestAccountsApi:
    """账户概览与分配预览 API 测试。"""

    def test_overview_returns_mock_accounts(self):
        """概览返回 mock 同步状态与账户行摘要。"""
        app = create_app(dist_dir=None)
        with TestClient(app) as test_client:
            response = test_client.get("/api/accounts/overview")
        assert response.status_code == 200
        payload = response.json()
        assert payload["sync_status"] == "mock"
        assert payload["last_synced_at"] is not None
        assert len(payload["accounts"]) == 22
        assert set(payload["accounts"][0]) == {
            "row",
            "name",
            "cid",
            "group",
            "enabled",
            "is_test",
            "drama_name",
        }

    def test_overview_uses_configured_real_account_source(self, monkeypatch):
        rows = [AccountRow(2, "真实账户", "real-cid", "B1", True, False, "")]
        monkeypatch.setattr(
            accounts_route,
            "_account_source",
            lambda: ("real", rows),
        )
        app = create_app(dist_dir=None)

        with TestClient(app) as test_client:
            response = test_client.get("/api/accounts/overview")

        assert response.status_code == 200
        assert response.json()["sync_status"] == "real"
        assert response.json()["accounts"][0]["cid"] == "real-cid"

    def test_allocate_preview_iaa_returns_first_available_block(self):
        """IAA 分配预览返回首个完整块，但不写入账户表。"""
        app = create_app(dist_dir=None)
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/accounts/allocate-preview",
                json={
                    "drama_name": "新剧",
                    "block_type": "IAA",
                    "allocated_cids": [],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["found"] is True
        assert body["block_type"] == "IAA"
        assert len(body["rows"]) == 10
        assert len(body["cids"]) == 10
        assert body["test_account_row"]["group"] == "B4"
        assert set(body["write_plan"]) == {str(i) for i in range(4, 14)}
        assert all(
            item["drama_name"] == "新剧"
            for item in body["write_plan"].values()
        )

    def test_allocate_preview_iap_returns_six_rows(self):
        """IAP 双模板分配预览返回 6 行完整块。"""
        app = create_app(dist_dir=None)
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/accounts/allocate-preview",
                json={
                    "drama_name": "新剧",
                    "block_type": "IAP",
                    "allocated_cids": [],
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["found"] is True
        assert body["block_type"] == "IAP"
        assert len(body["rows"]) == 6
        assert len(body["cids"]) == 6

    def test_allocate_preview_returns_not_found_when_block_allocated(self):
        """传入已分配 CID 时返回 found=false。"""
        app = create_app(dist_dir=None)
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/accounts/allocate-preview",
                json={
                    "drama_name": "新剧",
                    "block_type": "IAA",
                    "allocated_cids": ["MOCK-CID-IAA-1"],
                },
            )
        assert response.status_code == 200
        assert response.json() == {"found": False}

    def test_allocate_preview_does_not_write_accounts(self):
        """预览后概览账户行不变。"""
        app = create_app(dist_dir=None)
        with TestClient(app) as test_client:
            before = test_client.get("/api/accounts/overview").json()["accounts"]
            response = test_client.post(
                "/api/accounts/allocate-preview",
                json={
                    "drama_name": "新剧",
                    "block_type": "IAA",
                    "allocated_cids": [],
                },
            )
            assert response.status_code == 200
            after = test_client.get("/api/accounts/overview").json()["accounts"]
        assert before == after

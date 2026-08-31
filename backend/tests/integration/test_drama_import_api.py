"""剧目导入 API：预览、确认和运行记录。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.domain.imports.drama_import import PrivateDramaRow, PublicDramaRow
from backend.infrastructure.database.engine import create_app_engine
from backend.interfaces.api.main import create_app
from backend.interfaces.api.routes.drama_import import get_drama_sheet


def _public_row() -> PublicDramaRow:
    cells = [""] * 28
    cells[4] = "2026/8/17 10:00"
    cells[5] = "接口今日剧"
    cells[2] = "B田雨-林浩东"
    cells[10] = "番茄"
    return PublicDramaRow(row_number=7, cells=tuple(cells))


class FakeDramaSheet:
    def __init__(self) -> None:
        self.insert_calls = 0

    def read_public_rows(self, business_date: date) -> list[PublicDramaRow]:
        assert business_date == date(2026, 8, 17)
        return [_public_row()]

    def read_private_rows(self) -> list[tuple[str, ...]]:
        return []

    def private_revision(self) -> int:
        return 33

    def insert_private_rows(
        self, rows: list[PrivateDramaRow], *, expected_revision: int
    ) -> object:
        assert expected_revision == 33
        self.insert_calls += 1
        return type(
            "InsertResult",
            (),
            {"inserted_count": len(rows), "inserted_rows": (2,), "verified": True},
        )()


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_url = f"sqlite:///{tmp_path / 'drama_import_api.db'}"
    engine = create_app_engine(db_url)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("script_location", str(Path("alembic").resolve()))
    command.upgrade(config, "head")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(
        "backend.infrastructure.database.session.SessionLocal", factory
    )
    sheet = FakeDramaSheet()
    app = create_app(dist_dir=None)
    app.dependency_overrides[get_drama_sheet] = lambda: sheet
    with TestClient(app) as test_client:
        yield test_client, sheet
    engine.dispose()


def test_preview_confirm_and_run_query_are_idempotent(client) -> None:
    """若路由绕过确认或遗漏本地运行记录，测试必须失败。"""
    api, sheet = client

    preview = api.post(
        "/api/drama-import/preview", json={"business_date": "2026-08-17"}
    )

    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["new_count"] == 1
    assert preview_data["rows"][0]["drama_name"] == "接口今日剧"
    assert sheet.insert_calls == 0

    confirmed = api.post(
        "/api/drama-import/confirm", json={"preview_id": preview_data["preview_id"]}
    )
    repeated = api.post(
        "/api/drama-import/confirm", json={"preview_id": preview_data["preview_id"]}
    )
    run = api.get(f"/api/drama-import/runs/{preview_data['preview_id']}")

    assert confirmed.status_code == 200
    assert repeated.status_code == 200
    assert confirmed.json() == repeated.json()
    assert confirmed.json()["inserted_rows"] == [2]
    assert sheet.insert_calls == 1
    assert run.status_code == 200
    assert run.json()["status"] == "COMPLETED"
    assert run.json()["inserted_count"] == 1


def test_imported_records_list_returns_confirmed_drama_rows(client) -> None:
    api, _ = client
    preview = api.post(
        "/api/drama-import/preview", json={"business_date": "2026-08-17"}
    ).json()
    api.post("/api/drama-import/confirm", json={"preview_id": preview["preview_id"]})

    records = api.get(
        "/api/drama-import/records", params={"business_date": "2026-08-17"}
    )

    assert records.status_code == 200
    assert records.json()[0]["drama_name"] == "接口今日剧"
    assert records.json()[0]["available_time"] == "2026/8/17 10:00"
    assert records.json()[0]["operator_name"] == "田雨-林浩东"

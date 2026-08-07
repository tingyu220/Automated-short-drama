"""platform_login CLI 单元测试：使用 fake service。"""
from __future__ import annotations

from pathlib import Path

from backend.application.services.session_service import SessionService
from backend.interfaces.cli import platform_login as cli


class FakeSessionService:
    def __init__(self) -> None:
        self.cleared: list[str] = []

    def import_storage(self, platform: str, storage_state: dict) -> Path:
        return Path("sessions") / platform / "storage.json"

    def check(self, platform: str):
        return {
            "platform": platform,
            "status": "logged_in",
            "login_url": "https://example.com",
            "message": "ok",
            "expires_at": None,
            "storage_path": None,
        }

    def clear(self, platform: str) -> None:
        self.cleared.append(platform)


def test_import_command_uses_service(monkeypatch, capsys, tmp_path):
    fake = FakeSessionService()
    monkeypatch.setattr(cli, "SessionService", lambda: fake)
    storage_file = tmp_path / "storage.json"
    storage_file.write_text('{"cookies": []}', encoding="utf-8")

    code = cli.main(["import", "tomato", str(storage_file)])

    assert code == 0
    assert "已导入" in capsys.readouterr().out


def test_clear_command_uses_service(monkeypatch, capsys):
    fake = FakeSessionService()
    monkeypatch.setattr(cli, "SessionService", lambda: fake)

    code = cli.main(["clear", "ocean"])

    assert code == 0
    assert fake.cleared == ["ocean"]

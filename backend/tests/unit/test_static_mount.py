"""mount_frontend 静态挂载测试。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.interfaces.api.main import create_app
from backend.interfaces.api.main import mount_frontend


class TestMountFrontend:
    """mount_frontend 函数单元测试。"""

    def test_mount_frontend_none_no_exception(self):
        """dist_dir 为 None 时不抛异常。"""
        app = create_app(dist_dir=None)
        mount_frontend(app, None)

    def test_dist_exists_slash_returns_200(self):
        """dist 目录存在时 GET / 返回 200 且内容正确。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir)
            index_path = dist_dir / "index.html"
            index_path.write_text("<html><body>Hello</body></html>", encoding="utf-8")

            app = create_app(dist_dir=dist_dir)
            client = TestClient(app)

            response = client.get("/")
            assert response.status_code == 200
            assert "Hello" in response.text

    def test_dist_not_exists_no_exception(self):
        """dist 目录不存在时 mount_frontend 不抛异常。"""
        app = create_app(dist_dir=None)
        mount_frontend(app, Path("/nonexistent-dist-dir"))

    def test_dist_not_exists_healthz_ok(self):
        """dist 不存在时 /healthz 仍正常工作。"""
        app = create_app(dist_dir=None)
        client = TestClient(app)
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_mount_frontend_skips_when_not_dir(self, tmp_path):
        """dist_dir 不是目录（如文件）时静默跳过。"""
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("not a directory")
        app = create_app(dist_dir=None)
        mount_frontend(app, file_path)

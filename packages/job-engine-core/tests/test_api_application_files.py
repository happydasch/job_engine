"""
Tests for GET /api/applications/{app_id}/files/{filename:path}.

Regression: the path-traversal guard used a string-prefix check, so app 1 could
read app 12's archive ("data/archives/applications/12" starts with ".../1").
The route now uses ``Path.resolve()`` + ``is_relative_to``.
"""

import pytest
from fastapi import HTTPException


@pytest.fixture
def archives(tmp_path, monkeypatch):
    """Run from a tmp cwd holding archives for applications 1 and 12."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "data" / "archives" / "applications"
    for app_id in ("1", "12"):
        (root / app_id).mkdir(parents=True)
        (root / app_id / "x.pdf").write_bytes(f"%PDF app {app_id}".encode())
    (tmp_path / "secret.txt").write_text("top secret")
    return root


@pytest.fixture
def route():
    from dashboard.routes import applications

    return applications


class TestDownloadApplicationFile:
    @pytest.mark.asyncio
    async def test_valid_file_is_served(self, archives, route):
        resp = await route.download_application_file(1, "x.pdf")

        assert str(resp.path) == str((archives / "1" / "x.pdf").resolve())

    @pytest.mark.asyncio
    async def test_sibling_app_prefix_is_forbidden(self, archives, route):
        """App 1 must not read app 12's file even though '12' starts with '1'."""
        with pytest.raises(HTTPException) as exc:
            await route.download_application_file(1, "../12/x.pdf")

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename",
        ["../../../../secret.txt", "../../../../../../etc/passwd", "/etc/passwd"],
    )
    async def test_traversal_is_forbidden(self, archives, route, filename):
        with pytest.raises(HTTPException) as exc:
            await route.download_application_file(1, filename)

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_file_is_404(self, archives, route):
        with pytest.raises(HTTPException) as exc:
            await route.download_application_file(1, "nope.pdf")

        assert exc.value.status_code == 404


class TestDownloadApplicationFileHttp:
    """Same guarantees through the real ASGI app (encoded slashes survive the client)."""

    @pytest.fixture
    def client(self, archives):
        from dashboard.main import app
        from fastapi.testclient import TestClient

        with TestClient(app) as c:
            yield c

    def test_valid_file_is_served(self, client):
        resp = client.get("/api/applications/1/files/x.pdf")

        assert resp.status_code == 200
        assert resp.content == b"%PDF app 1"

    def test_sibling_app_prefix_is_forbidden(self, client):
        resp = client.get("/api/applications/1/files/..%2F12%2Fx.pdf")

        assert resp.status_code == 403

    def test_etc_traversal_is_forbidden(self, client):
        resp = client.get("/api/applications/1/files/..%2F..%2F..%2F..%2F..%2Fetc%2Fpasswd")

        assert resp.status_code == 403

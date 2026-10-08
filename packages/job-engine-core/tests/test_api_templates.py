"""Tests for POST /api/templates/register — template name validation."""

import pytest

DOC = rb"\documentclass{article}\begin{document}x\end{document}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from dashboard.main import app
    from dashboard.routes import templates
    from fastapi.testclient import TestClient

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(templates, "TEMPLATES_DIR", tmp_path / "templates")
    (tmp_path / "templates").mkdir()
    monkeypatch.setattr(templates, "compile_latex", lambda *a, **kw: str(tmp_path / "x.pdf"))
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("name", ["../evil", "../../x", "a/b", "..", ".hidden", "a\\b"])
def test_traversal_names_are_rejected(client, tmp_path, name):
    resp = client.post(
        "/api/templates/register",
        files={"file": ("t.tex", DOC, "application/x-tex")},
        data={"name": name},
    )

    assert resp.status_code == 400
    assert not (tmp_path / "evil.tex").exists()
    assert not (tmp_path / "x.tex").exists()


def test_valid_name_is_saved(client, tmp_path):
    resp = client.post(
        "/api/templates/register",
        files={"file": ("t.tex", DOC, "application/x-tex")},
        data={"name": "my-cv_v2"},
    )

    assert resp.status_code == 200, resp.text
    assert (tmp_path / "templates" / "my-cv_v2.tex").exists()

"""
Tests for the LaTeX/PDF pipeline in ``job_engine.latex_compiler``.

``tectonic`` and ``pdftotext`` are mocked via ``subprocess.run`` so the suite
runs without either binary installed. One real-compile test runs only when
``tectonic`` is on PATH.
"""

import shutil
import subprocess
from types import SimpleNamespace

import pytest
from job_engine import latex_compiler
from job_engine.latex_compiler import (
    LatexError,
    ats_verify_pdf,
    compile_latex,
    extract_text_from_pdf,
    verify_cover_letter,
    verify_cv,
)

MINIMAL_TEX = r"""\documentclass{article}
\begin{document}
Hello PDF
\end{document}
"""


def _completed(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _patch_run(monkeypatch, *, result=None, exc=None, calls=None, side_effect=None):
    """Replace ``subprocess.run`` inside latex_compiler."""

    def fake_run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        if side_effect is not None:
            return side_effect(cmd)
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(latex_compiler.subprocess, "run", fake_run)


def _pdftotext_output(monkeypatch, stdout: str, returncode: int = 0):
    _patch_run(monkeypatch, result=_completed(returncode=returncode, stdout=stdout))


# ─── compile_latex ──────────────────────────────────────────────────────────


class TestCompileLatex:
    def test_success_writes_tex_and_returns_pdf_path(self, tmp_path, monkeypatch):
        calls: list = []

        def tectonic(cmd):
            (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.5 fake")
            return _completed()

        _patch_run(monkeypatch, calls=calls, side_effect=tectonic)

        result = compile_latex(MINIMAL_TEX, tmp_path, name="cv")

        assert result == str((tmp_path / "cv.pdf").resolve())
        assert (tmp_path / "cv.tex").read_text(encoding="utf-8") == MINIMAL_TEX
        cmd, kwargs = calls[0]
        assert cmd == ["tectonic", str(tmp_path / "cv.tex")]
        assert kwargs["timeout"] == 120

    def test_creates_missing_output_dir(self, tmp_path, monkeypatch):
        out = tmp_path / "nested" / "dir"

        def tectonic(cmd):
            (out / "output.pdf").write_bytes(b"%PDF")
            return _completed()

        _patch_run(monkeypatch, side_effect=tectonic)

        assert compile_latex(MINIMAL_TEX, str(out)) == str((out / "output.pdf").resolve())

    def test_nonzero_exit_raises(self, tmp_path, monkeypatch):
        _patch_run(monkeypatch, result=_completed(returncode=1, stderr="! Undefined control"))

        with pytest.raises(LatexError, match="Undefined control"):
            compile_latex(MINIMAL_TEX, tmp_path)

    def test_tectonic_missing_raises(self, tmp_path, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError("tectonic"))

        with pytest.raises(LatexError, match="not found on PATH"):
            compile_latex(MINIMAL_TEX, tmp_path)

    def test_timeout_raises(self, tmp_path, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="tectonic", timeout=120))

        with pytest.raises(LatexError, match="timed out"):
            compile_latex(MINIMAL_TEX, tmp_path)

    def test_success_without_any_pdf_raises(self, tmp_path, monkeypatch):
        _patch_run(monkeypatch, result=_completed())

        with pytest.raises(LatexError, match="no PDF found"):
            compile_latex(MINIMAL_TEX, tmp_path, name="cv")

    def test_falls_back_to_other_pdf_in_dir(self, tmp_path, monkeypatch):
        def tectonic(cmd):
            (tmp_path / "other.pdf").write_bytes(b"%PDF")
            return _completed()

        _patch_run(monkeypatch, side_effect=tectonic)

        assert compile_latex(MINIMAL_TEX, tmp_path, name="cv") == str(
            (tmp_path / "other.pdf").resolve()
        )

    @pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")
    def test_real_compile(self, tmp_path):
        pdf = compile_latex(MINIMAL_TEX, tmp_path, name="real")

        assert pdf is not None
        assert pdf.endswith("real.pdf")
        with open(pdf, "rb") as f:
            assert f.read(4) == b"%PDF"


# ─── verify_cv / verify_cover_letter ────────────────────────────────────────


class TestVerifyCv:
    def test_two_pages_ok(self, monkeypatch):
        text = "Jane Doe\nExperience\nDid things.\n\x0cMore content here.\nAnd more.\n\x0c"
        _pdftotext_output(monkeypatch, text)

        assert verify_cv("cv.pdf") == {"ok": True, "pages": 2, "issues": []}

    def test_wrong_page_count_flagged(self, monkeypatch):
        _pdftotext_output(monkeypatch, "only page content.\n\x0c")

        result = verify_cv("cv.pdf")

        assert result["ok"] is False
        assert result["pages"] == 1
        assert "expected exactly 2" in result["issues"][0]

    def test_orphaned_section_title_flagged(self, monkeypatch):
        text = "Summary of things.\nExperience\x0cOne line only.\x0c"
        _pdftotext_output(monkeypatch, text)

        result = verify_cv("cv.pdf")

        assert result["pages"] == 2
        assert result["ok"] is False
        assert any("orphaned title on page 1: 'Experience'" in i for i in result["issues"])

    def test_pdftotext_missing(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError("pdftotext"))

        with pytest.raises(LatexError, match="pdftotext not found"):
            verify_cv("cv.pdf")

    def test_pdftotext_failure(self, monkeypatch):
        _pdftotext_output(monkeypatch, "", returncode=1)

        with pytest.raises(LatexError, match="exit code 1"):
            verify_cv("cv.pdf")


class TestVerifyCoverLetter:
    def test_one_page_ok(self, monkeypatch):
        _pdftotext_output(monkeypatch, "Dear Hiring Team,\nBody.\n\x0c")

        assert verify_cover_letter("cl.pdf") == {"ok": True, "pages": 1, "issues": []}

    def test_no_form_feed_counts_as_one_page(self, monkeypatch):
        _pdftotext_output(monkeypatch, "Dear Hiring Team")

        assert verify_cover_letter("cl.pdf")["pages"] == 1

    def test_two_pages_flagged(self, monkeypatch):
        _pdftotext_output(monkeypatch, "a\x0cb\x0c")

        result = verify_cover_letter("cl.pdf")

        assert result["ok"] is False
        assert result["pages"] == 2
        assert "expected exactly 1" in result["issues"][0]

    def test_page_count_unavailable(self, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="pdftotext", timeout=30))

        with pytest.raises(LatexError, match="timed out"):
            verify_cover_letter("cl.pdf")


# ─── extract_text_from_pdf ──────────────────────────────────────────────────


class TestExtractTextFromPdf:
    def test_replaces_form_feeds_with_page_markers(self, monkeypatch):
        calls: list = []
        _patch_run(monkeypatch, result=_completed(stdout="one\x0ctwo"), calls=calls)

        assert extract_text_from_pdf("x.pdf") == "one\n--- PAGE BREAK ---\ntwo"
        assert calls[0][0] == ["pdftotext", "x.pdf", "-"]

    def test_failure_raises(self, monkeypatch):
        _pdftotext_output(monkeypatch, "", returncode=3)

        with pytest.raises(LatexError, match="exit code 3"):
            extract_text_from_pdf("x.pdf")

    def test_missing_binary_raises(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError("pdftotext"))

        with pytest.raises(LatexError, match="pdftotext not found"):
            extract_text_from_pdf("x.pdf")


# ─── ats_verify_pdf ─────────────────────────────────────────────────────────


class TestAtsVerifyPdf:
    def test_keywords_and_contact_detected(self, monkeypatch):
        text = "Jane Doe\njane.doe@example.com\n+48 123 456 789\nPython, FastAPI, Docker\x0c"
        _pdftotext_output(monkeypatch, text)

        result = ats_verify_pdf("cv.pdf", ["python", "FASTAPI", "kubernetes", "docker"])

        assert result["has_text_layer"] is True
        assert result["keyword_coverage_pct"] == 75.0
        assert result["keywords_matched"] == ["python", "FASTAPI", "docker"]
        assert result["has_email"] is True
        assert result["has_phone"] is True
        assert result["has_contact"] is True
        assert result["issues"] == []

    def test_no_contact_details(self, monkeypatch):
        _pdftotext_output(monkeypatch, "Python developer")

        result = ats_verify_pdf("cv.pdf", ["python"])

        assert result["has_contact"] is False
        assert result["has_email"] is False
        assert result["has_phone"] is False
        assert result["keyword_coverage_pct"] == 100.0

    def test_empty_keyword_list(self, monkeypatch):
        _pdftotext_output(monkeypatch, "Python developer")

        assert ats_verify_pdf("cv.pdf", [])["keyword_coverage_pct"] == 0.0

    def test_no_text_layer(self, monkeypatch):
        _pdftotext_output(monkeypatch, "  \n\x0c  ")

        result = ats_verify_pdf("cv.pdf", ["python"])

        assert result["has_text_layer"] is False
        assert result["keyword_coverage_pct"] == 0.0
        assert result["has_contact"] is False

    def test_no_text_layer_reports_issue_in_list(self, monkeypatch):
        _pdftotext_output(monkeypatch, "")

        result = ats_verify_pdf("cv.pdf", ["python"])

        assert isinstance(result["issues"], list)
        assert len(result["issues"]) == 1
        assert "no extractable text layer" in result["issues"][0]

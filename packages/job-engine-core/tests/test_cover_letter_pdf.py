"""
Tests for ``job_engine.cover_letter_pdf.wrap_cover_letter``.

``compile_latex`` is replaced with a recorder so no LaTeX toolchain is needed.
"""

import pytest
from job_engine import cover_letter_pdf
from job_engine.cover_letter_pdf import wrap_cover_letter


@pytest.fixture
def compiled(monkeypatch):
    """Capture the arguments passed to compile_latex."""
    calls: list[dict] = []

    def fake_compile(tex, output_dir, name="output"):
        calls.append({"tex": tex, "output_dir": output_dir, "name": name})
        return f"/fake/{name}.pdf"

    monkeypatch.setattr(cover_letter_pdf, "compile_latex", fake_compile)
    return calls


class TestWrapCoverLetter:
    def test_fills_template_and_compiles(self, compiled, tmp_path):
        result = wrap_cover_letter(
            "First paragraph.\n\nSecond paragraph.",
            tmp_path,
            name="cl",
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            phone="+48 123",
            company="TechCorp",
            address="Warsaw",
        )

        assert result == "/fake/cl.pdf"
        assert len(compiled) == 1
        call = compiled[0]
        assert call["output_dir"] == tmp_path
        assert call["name"] == "cl"
        tex = call["tex"]
        assert r"\firstname{Jane}" in tex
        assert r"\familyname{Doe}" in tex
        assert r"\email{jane@example.com}" in tex
        assert r"\phone{+48 123}" in tex
        assert r"\recipient{TechCorp}{Warsaw}" in tex
        assert "First paragraph.\n\nSecond paragraph." in tex
        assert "%%" not in tex
        assert tex.index(r"\makelettertitle") < tex.index("First paragraph.")
        assert tex.index("Second paragraph.") < tex.index(r"\makeletterclosing")

    def test_defaults(self, compiled, tmp_path):
        wrap_cover_letter("Body.", tmp_path)

        call = compiled[0]
        assert call["name"] == "cover_letter"
        assert r"\firstname{}" in call["tex"]
        assert r"\recipient{}{}" in call["tex"]

    def test_paragraphs_are_stripped(self, compiled, tmp_path):
        wrap_cover_letter("\n\n  Para one.  \n\n   Para two.\n\n", tmp_path)

        assert "Para one.\n\nPara two." in compiled[0]["tex"]

    def test_compile_failure_propagates_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cover_letter_pdf, "compile_latex", lambda *a, **k: None)

        assert wrap_cover_letter("Body.", tmp_path) is None

    def test_latex_special_characters_are_escaped(self, compiled, tmp_path):
        wrap_cover_letter(
            "I improved revenue by 50% & cut costs by $10k_#1.",
            tmp_path,
            company="Smith & Sons",
        )

        tex = compiled[0]["tex"]
        assert r"50\%" in tex
        assert r"\&" in tex
        assert r"\$10k" in tex
        assert r"\recipient{Smith \& Sons}" in tex

    def test_latex_commands_in_text_are_neutralised(self, compiled, tmp_path):
        wrap_cover_letter(r"Hi \input{/etc/passwd} there", tmp_path, first_name="A_{b}")

        tex = compiled[0]["tex"]
        assert r"\input{/etc/passwd}" not in tex
        assert r"\textbackslash{}input\{/etc/passwd\}" in tex
        assert r"\firstname{A\_\{b\}}" in tex

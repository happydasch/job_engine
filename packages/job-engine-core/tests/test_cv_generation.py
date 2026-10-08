"""
Tests for CV generation in ``job_engine.llm``: ``generate_cv`` and ``_trim_cv_to_fit``.

The LLM is never called: ``get_llm`` and ``_safe_invoke`` are mocked.
"""

import json
from unittest.mock import MagicMock

import pytest
from job_engine import llm
from job_engine.llm import _trim_cv_to_fit, generate_cv

PREAMBLE = [
    r"\documentclass[11pt,a4paper]{moderncv}",
    r"\moderncvstyle{banking}",
    r"\begin{document}",
]
POSTAMBLE = [r"\end{document}"]


def _job() -> dict:
    return {
        "title": "Senior Python Engineer",
        "company": "TechCorp",
        "description": "Build trading systems with FastAPI.",
        "skills": ["python", "fastapi"],
    }


def _cv(body: list[str]) -> str:
    return "\n".join(PREAMBLE + body + POSTAMBLE)


class FakeProfileConfig:
    """Stand-in for ProfileConfig that never touches disk."""

    loaded = 0

    def load(self) -> dict:
        FakeProfileConfig.loaded += 1
        return {"name": "Loaded Candidate", "skills": {"backend": ["python"]}}

    def load_cv(self) -> str:
        return "Existing CV text"


@pytest.fixture
def cv_env(monkeypatch):
    """Mock the LLM plumbing; return a dict whose 'response' the test sets."""
    state: dict = {"response": (None, "invocation_error"), "messages": None}

    def fake_invoke(llm_obj, messages, pydantic_parser=None):
        state["messages"] = messages
        return state["response"]

    FakeProfileConfig.loaded = 0
    monkeypatch.setattr(llm, "get_llm", lambda: MagicMock(name="llm"))
    monkeypatch.setattr(llm, "_safe_invoke", fake_invoke)
    monkeypatch.setattr(llm, "_get_settings_language", lambda: "English")
    monkeypatch.setattr(llm, "ProfileConfig", FakeProfileConfig)
    return state


# ─── generate_cv ────────────────────────────────────────────────────────────


class TestGenerateCv:
    def test_returns_none_without_llm(self, monkeypatch):
        monkeypatch.setattr(llm, "get_llm", lambda: None)
        invoke = MagicMock()
        monkeypatch.setattr(llm, "_safe_invoke", invoke)

        assert generate_cv(_job(), profile={"name": "X"}) is None
        invoke.assert_not_called()

    def test_returns_none_on_invocation_error(self, cv_env):
        cv_env["response"] = (None, "invocation_error")

        assert generate_cv(_job(), profile={"name": "X"}) is None

    def test_returns_none_on_unparseable_output(self, cv_env):
        cv_env["response"] = ("this is not json at all", None)

        assert generate_cv(_job(), profile={"name": "X"}) is None

    def test_success_returns_parsed_and_trims(self, cv_env, monkeypatch):
        payload = {
            "cv_latex": _cv([r"\section{Experience}"]),
            "skills_covered": ["python"],
            "skills_gapped": [],
            "summary": "Strong match",
        }
        cv_env["response"] = (f"```json\n{json.dumps(payload)}\n```", None)
        trim_calls: list[str] = []

        def fake_trim(cv_latex, max_lines=45):
            trim_calls.append(cv_latex)
            return "TRIMMED"

        monkeypatch.setattr(llm, "_trim_cv_to_fit", fake_trim)

        result = generate_cv(_job(), profile={"name": "Jane Doe"}, language="Polish")

        assert result is not None
        assert result["cv_latex"] == "TRIMMED"
        assert result["skills_covered"] == ["python"]
        assert result["summary"] == "Strong match"
        assert trim_calls == [payload["cv_latex"]]
        rendered = "\n".join(m.content for m in cv_env["messages"])
        assert "Jane Doe" in rendered
        assert "Polish" in rendered
        assert "Existing CV text" in rendered
        assert FakeProfileConfig.loaded == 0

    def test_missing_cv_latex_skips_trim(self, cv_env, monkeypatch):
        cv_env["response"] = (json.dumps({"summary": "no latex"}), None)
        trim = MagicMock()
        monkeypatch.setattr(llm, "_trim_cv_to_fit", trim)

        assert generate_cv(_job(), profile={"name": "X"}) == {"summary": "no latex"}
        trim.assert_not_called()

    def test_profile_none_loads_profile_config(self, cv_env):
        cv_env["response"] = (json.dumps({"cv_latex": "", "summary": "ok"}), None)

        result = generate_cv(_job())

        assert result == {"cv_latex": "", "summary": "ok"}
        assert FakeProfileConfig.loaded == 1
        rendered = "\n".join(m.content for m in cv_env["messages"])
        assert "Loaded Candidate" in rendered


# ─── _trim_cv_to_fit ────────────────────────────────────────────────────────


class TestTrimCvToFit:
    def test_empty_string_passthrough(self):
        assert _trim_cv_to_fit("") == ""

    def test_noop_under_limit(self):
        cv = _cv([r"\item short"] * 5)

        assert _trim_cv_to_fit(cv, max_lines=10) is cv

    def test_noop_at_exact_limit(self):
        cv = _cv([r"\item short"] * 10)

        assert _trim_cv_to_fit(cv, max_lines=10) == cv

    def test_removes_short_items_first(self):
        long_item = r"\item " + "Delivered a substantial, measurable business outcome" * 2
        body = [r"\section{Experience}", long_item, r"\item short A", long_item, r"\item short B"]
        cv = _cv(body)

        result = _trim_cv_to_fit(cv, max_lines=3)
        lines = result.split("\n")

        assert r"\item short A" not in lines
        assert r"\item short B" not in lines
        assert lines.count(long_item) == 2
        assert r"\section{Experience}" in lines

    def test_removes_only_as_many_as_needed(self):
        body = [r"\item keep 1", r"\item keep 2", r"\item drop 3"]
        result = _trim_cv_to_fit(_cv(body), max_lines=2)
        lines = result.split("\n")

        assert r"\item drop 3" not in lines
        assert r"\item keep 1" in lines
        assert r"\item keep 2" in lines

    def test_removes_empty_cvitem(self):
        body = [r"\section{Skills}", r"\cvitem{Languages}{}", r"\cvitem{Python}{Expert level}"]
        result = _trim_cv_to_fit(_cv(body), max_lines=2)

        assert r"\cvitem{Languages}{}" not in result
        assert r"\cvitem{Python}{Expert level}" in result

    def test_falls_back_to_trailing_long_items(self):
        long_a = r"\item " + "A" * 60
        long_b = r"\item " + "B" * 60
        body = [r"\section{Experience}", long_a, long_b]
        result = _trim_cv_to_fit(_cv(body), max_lines=2)

        assert long_b not in result
        assert long_a in result

    def test_preserves_preamble_and_end_document(self):
        body = [r"\item x"] * 50
        result = _trim_cv_to_fit(_cv(body), max_lines=45)
        lines = result.split("\n")

        assert lines[: len(PREAMBLE)] == PREAMBLE
        assert lines[-1] == r"\end{document}"
        body_lines = lines[len(PREAMBLE) : -1]
        assert len(body_lines) == 45

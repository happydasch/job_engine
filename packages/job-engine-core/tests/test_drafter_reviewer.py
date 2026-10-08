"""Regression tests: reviewer/ATS prompts must format without KeyError."""

import json

from job_engine import drafter_reviewer
from job_engine._sanitize import SANITIZE_FORBIDDANCE


def _capture(monkeypatch, reply):
    sent = []

    def fake_invoke(_llm, messages):
        sent.append(messages)
        return reply, None

    monkeypatch.setattr(drafter_reviewer, "get_llm", lambda: object())
    monkeypatch.setattr(drafter_reviewer, "_safe_invoke", fake_invoke)
    return sent


def test_generate_with_review_includes_forbiddance(monkeypatch):
    sent = _capture(monkeypatch, json.dumps({"overall_assessment": "approved", "issues": []}))

    draft, error = drafter_reviewer.generate_with_review(
        lambda: ("Dear team", None), job_context="job", profile_context="me"
    )

    assert (draft, error) == ("Dear team", None)
    assert SANITIZE_FORBIDDANCE in sent[0][1].content


def test_verify_ats_includes_forbiddance(monkeypatch):
    sent = _capture(monkeypatch, json.dumps({"overall_ok": True}))

    drafter_reviewer.verify_ats("Dear team", ["python"])

    assert SANITIZE_FORBIDDANCE in sent[0][1].content

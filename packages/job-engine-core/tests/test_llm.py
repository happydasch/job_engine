"""
Tests for the LLM integration module.

These tests mock the actual LLM calls to avoid API costs and rate limits.
"""

import json
from unittest.mock import MagicMock, patch


def _clear_api_key(monkeypatch, value=""):
    """Make _resolve_provider() report no API key configured."""
    monkeypatch.setattr(
        "job_engine.llm._resolve_provider", lambda: ("openrouter", value, "openai/gpt-4o-mini")
    )


def _set_api_key(monkeypatch, value="sk-or-v1-test-key"):
    monkeypatch.setattr(
        "job_engine.llm._resolve_provider", lambda: ("openrouter", value, "openai/gpt-4o-mini")
    )


def _sample_job() -> dict:
    return {
        "external_id": "test_llm_001",
        "platform": "justjoin.it",
        "title": "Senior Python Backend Engineer",
        "company": "TechCorp",
        "url": "https://example.com/job/1",
        "description": (
            "We are looking for a senior Python developer to build "
            "our trading platform. You'll work with FastAPI, PostgreSQL, "
            "Redis, and deploy on AWS. Experience with financial markets "
            "is a plus."
        ),
        "salary_min": 25000,
        "salary_max": 45000,
        "currency": "USD",
        "contract_type": "full_time",
        "location": "Remote",
        "remote": True,
        "skills": ["python", "fastapi", "postgresql", "redis", "aws"],
        "category": "python",
        "experience_level": "senior",
        "match_score": 85.0,
        "match_details": {
            "components": {
                "skill_overlap": {"score": 90, "weight": 0.60},
                "keyword_boost": {"score": 80, "weight": 0.40},
            }
        },
    }


class TestGetLLM:
    """Tests for get_llm()."""

    def test_returns_none_when_no_api_key(self, monkeypatch):
        """Should return None when no API key is configured."""
        _clear_api_key(monkeypatch)

        import job_engine.llm as llm_mod

        llm_mod._llm = None

        result = llm_mod.get_llm()
        assert result is None

    def test_returns_instance_when_key_present(self, monkeypatch):
        """Should not be None when key is set (may be None if langchain missing)."""
        _set_api_key(monkeypatch)

        import job_engine.llm as llm_mod

        llm_mod._llm = None

        result = llm_mod.get_llm()
        # If langchain is installed, it should be an object with invoke
        if result is not None:
            assert hasattr(result, "invoke")


class TestMakeJobContext:
    """Tests for _make_job_context."""

    def test_formats_job_context(self):
        """Should include title, company, tech stack, description."""
        from job_engine.llm import _make_job_context

        job = _sample_job()
        context = _make_job_context(job)

        assert "Senior Python Backend Engineer" in context
        assert "TechCorp" in context
        assert "python, fastapi, postgresql, redis, aws" in context
        assert "Remote" in context
        assert "trading platform" in context

    def test_handles_missing_fields(self):
        """Should handle jobs with missing fields gracefully."""
        from job_engine.llm import _make_job_context

        job = {"title": "Dev", "company": "Co"}
        context = _make_job_context(job)

        assert "Dev" in context
        assert "Co" in context
        assert "N/A" in context  # for missing fields

    def test_truncates_long_description(self):
        """Should truncate description to 8000 chars."""
        from job_engine.llm import _make_job_context

        job = _sample_job()
        job["description"] = "x" * 10000
        context = _make_job_context(job)

        # Description should be truncated
        assert len(context) < 9000


class TestAnalyzeJob:
    """Tests for analyze_job()."""

    def test_returns_none_when_no_llm(self, monkeypatch):
        """Should return None when LLM is unavailable."""
        _clear_api_key(monkeypatch)

        import job_engine.llm as llm_mod

        llm_mod._llm = None

        result = llm_mod.analyze_job(_sample_job())
        assert result is None

    @patch("job_engine.llm.get_llm")
    def test_returns_parsed_analysis(self, mock_get_llm):
        """Should parse LLM JSON response into structured dict."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "key_skills": ["python", "fastapi", "postgresql"],
                "nice_to_have": ["trading", "aws"],
                "seniority": "senior",
                "responsibilities": ["Build APIs", "Design DB schema"],
                "skills_inferred": ["fastapi", "postgresql", "redis"],
                "red_flags": ["Below-market salary range"],
                "relevance_notes": "Good match for the candidate.",
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        import job_engine.llm as llm_mod

        result = llm_mod.analyze_job(_sample_job())

        assert result is not None
        assert "python" in result.get("key_skills", [])
        assert result.get("seniority") == "senior"
        assert len(result.get("red_flags", [])) == 1
        assert "Good match" in result.get("relevance_notes", "")

    @patch("job_engine.llm.get_llm")
    def test_handles_json_in_code_block(self, mock_get_llm):
        """Should extract JSON from markdown code blocks."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            "Here's the analysis:\n\n```json\n"
            '{"key_skills": ["python", "fastapi"], "seniority": "mid"}\n'
            "```"
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        import job_engine.llm as llm_mod

        result = llm_mod.analyze_job(_sample_job())

        assert result is not None
        assert result.get("key_skills") == ["python", "fastapi"]


class TestExplainMatch:
    """Tests for explain_match()."""

    @patch("job_engine.llm.get_llm")
    def test_returns_explanation(self, mock_get_llm):
        """Should return strengths, gaps, recommendation."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "summary": "Strong match overall",
                "strengths": ["Python expertise aligns", "Remote-friendly"],
                "gaps": ["No Kubernetes experience"],
                "recommendation": "strong_match",
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        import job_engine.llm as llm_mod

        job = _sample_job()
        result = llm_mod.explain_match(job, job.get("match_details"))

        assert result is not None
        assert result["recommendation"] == "strong_match"
        assert "Python expertise" in result["strengths"][0]


class TestSummarizeJob:
    """Tests for summarize_job()."""

    @patch("job_engine.llm.get_llm")
    def test_returns_summary(self, mock_get_llm):
        """Should return a plain text summary string."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            "A fintech company is hiring a senior Python dev for their trading platform."
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        import job_engine.llm as llm_mod

        result = llm_mod.summarize_job(_sample_job())

        assert result is not None
        assert "fintech" in result.lower() or "trading" in result.lower()


class TestCoverLetter:
    """Tests for generate_cover_letter()."""

    @patch("job_engine.llm.get_llm")
    def test_includes_profile_context(self, mock_get_llm):
        """Should include profile skills in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Dear Hiring Manager..."
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        import job_engine.llm as llm_mod

        profile = {
            "role": "Backend Python Developer",
            "skills": {"core": ["python", "fastapi"]},
            "experience_years": 5,
            "rate": {"min_pln_net": 25000, "max_pln_net": 45000},
            "experience": [{"name": "Trading Bot", "description": "A trading bot"}],
        }
        result = llm_mod.generate_cover_letter(_sample_job(), profile)

        assert result is not None
        assert "Dear" in result


class TestInterviewQuestions:
    """Tests for suggest_interview_questions()."""

    @patch("job_engine.llm.get_llm")
    def test_returns_questions(self, mock_get_llm):
        """Should return a list of questions."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            [
                "Explain Python async/await",
                "Design a rate limiter",
                "How would you optimize a slow PostgreSQL query?",
            ]
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        import job_engine.llm as llm_mod

        result = llm_mod.suggest_interview_questions(_sample_job())

        assert result is not None
        assert len(result) == 3
        assert "Python async" in result[0]


class TestParseJson:
    """Tests for _parse_json()."""

    def test_parses_plain_json(self):
        """Should parse plain JSON strings."""
        from job_engine.llm import _parse_json

        parsed, raw = _parse_json('{"key": "value"}')
        assert parsed == {"key": "value"}

    def test_parses_json_array(self):
        """Should parse JSON arrays."""
        from job_engine.llm import _parse_json

        parsed, raw = _parse_json('["a", "b"]')
        assert parsed == ["a", "b"]

    def test_parses_json_in_code_block(self):
        """Should extract JSON from markdown code blocks."""
        from job_engine.llm import _parse_json

        parsed, raw = _parse_json('Here:\n\n```json\n{"k": "v"}\n```')
        assert parsed == {"k": "v"}

    def test_returns_none_on_invalid_json(self):
        """Should return (None, cleaned_text) on invalid JSON."""
        from job_engine.llm import _parse_json

        parsed, raw = _parse_json("not json at all")
        assert parsed is None
        assert raw == "not json at all"


class TestSafeInvoke:
    """Tests for _safe_invoke()."""

    def test_returns_no_key_error_when_llm_is_none_and_no_key(self, monkeypatch):
        """Should return (None, 'no_key') when LLM is None and no API key."""
        _clear_api_key(monkeypatch)
        from job_engine.llm import _safe_invoke

        result, error = _safe_invoke(None, "test prompt")
        assert result is None
        assert error == "no_key"

    def test_returns_invocation_error_when_llm_is_none_but_key_set(self, monkeypatch):
        """Should return (None, 'invocation_error') when LLM is None despite key."""
        _set_api_key(monkeypatch)
        from job_engine.llm import _safe_invoke

        result, error = _safe_invoke(None, "test prompt")
        assert result is None
        assert error == "invocation_error"

    def test_returns_empty_response_error(self, monkeypatch):
        """Should return (None, 'empty_response') on empty content."""
        _set_api_key(monkeypatch)
        from job_engine.llm import _safe_invoke

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "   "
        mock_llm.invoke.return_value = mock_response

        result, error = _safe_invoke(mock_llm, "test prompt")
        assert result is None
        assert error == "empty_response"

    def test_returns_content_on_success(self, monkeypatch):
        """Should return (content, None) on success."""
        _set_api_key(monkeypatch)
        from job_engine.llm import _safe_invoke

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "  actual result  "
        mock_llm.invoke.return_value = mock_response

        result, error = _safe_invoke(mock_llm, "test prompt")
        assert result == "actual result"
        assert error is None

    def test_returns_invocation_error_on_exception(self, monkeypatch):
        """Should return (None, 'invocation_error') on exception."""
        _set_api_key(monkeypatch)
        from job_engine.llm import _safe_invoke

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API Error")

        result, error = _safe_invoke(mock_llm, "test prompt")
        assert result is None
        assert error == "invocation_error"


class TestAnalyzeAllJob:
    """Tests for analyze_all_job() — the combined single-LLM-request function."""

    def test_returns_none_when_no_llm(self, monkeypatch):
        """Should return None when LLM is unavailable."""
        from job_engine.llm import analyze_all_job

        _clear_api_key(monkeypatch)
        import job_engine.llm as llm_mod

        llm_mod._llm = None

        result = analyze_all_job(_sample_job())
        assert result is None

    @patch("job_engine.llm.get_llm")
    def test_returns_combined_analysis(self, mock_get_llm):
        """Should return the full combined dict with all 5 keys."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "analysis": {
                    "key_skills": ["python", "fastapi", "postgresql"],
                    "nice_to_have": ["trading"],
                    "seniority": "senior",
                    "responsibilities": ["Build APIs"],
                    "skills_inferred": ["fastapi"],
                    "red_flags": [],
                    "relevance_notes": "Good match",
                },
                "summary": "A fintech company hiring a senior Python dev.",
                "explain_match": {
                    "summary": "Strong match",
                    "strengths": ["Python expertise"],
                    "gaps": ["No Kubernetes"],
                    "recommendation": "strong_match",
                },
                "cover_letter": "Dear Hiring Manager...",
                "questions": ["Explain async/await", "Design a rate limiter"],
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import analyze_all_job

        result = analyze_all_job(_sample_job())

        assert result is not None
        assert "analysis" in result
        assert "summary" in result
        assert "explain_match" in result
        assert "cover_letter" in result
        assert "questions" in result
        assert result["analysis"]["seniority"] == "senior"
        assert result["explain_match"]["recommendation"] == "strong_match"
        assert "Dear" in result["cover_letter"]

    @patch("job_engine.llm.get_llm")
    def test_accepts_optional_profile(self, mock_get_llm):
        """Should accept an optional profile parameter."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "analysis": {"key_skills": ["python"], "seniority": "mid"},
                "summary": "A job.",
                "explain_match": {
                    "summary": "Ok",
                    "strengths": [],
                    "gaps": [],
                    "recommendation": "possible",
                },
                "cover_letter": "Dear...",
                "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"],
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import analyze_all_job

        profile = {
            "role": "Backend Python Developer",
            "skills": {"core": ["python", "fastapi"]},
            "experience_years": 5,
            "rate": {"min_monthly": 25000, "max_monthly": 45000},
            "experience": [{"name": "Trading Bot", "description": "A trading bot"}],
        }
        result = analyze_all_job(_sample_job(), profile=profile)
        assert result is not None
        assert result["analysis"]["seniority"] == "mid"
        assert len(result["questions"]) == 5

    @patch("job_engine.llm.get_llm")
    def test_warns_on_missing_keys(self, mock_get_llm):
        """Should log a warning but not fail when keys are missing."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "analysis": {"key_skills": ["python"], "seniority": "mid"},
                "summary": "A job.",
                # Missing explain_match, cover_letter, questions
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import analyze_all_job

        result = analyze_all_job(_sample_job())
        # Should still return partial result (not None)
        assert result is not None
        assert "analysis" in result
        assert "summary" in result
        # Missing keys are just absent — no crash

    @patch("job_engine.llm.get_llm")
    def test_returns_none_on_parse_failure(self, mock_get_llm):
        """Should return None if JSON can't be parsed."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is not JSON at all"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import analyze_all_job

        result = analyze_all_job(_sample_job())
        assert result is None


class TestTryFixTruncatedJson:
    """Tests for _try_fix_truncated_json()."""

    def test_handles_braces_inside_strings(self):
        """Should not count braces inside string values."""
        from job_engine.llm import _try_fix_truncated_json

        # JSON with braces inside string values — should not incorrectly add extra closing braces
        snippet = '{"key": "some { text with } brace", "key2": "ok"}'
        result = _try_fix_truncated_json(snippet)
        assert result is None, "Should return None when no fix needed (valid JSON)"

    def test_closes_truncated_string_properly(self):
        """Should close unclosed string at end."""
        from job_engine.llm import _try_fix_truncated_json

        snippet = '{"name": "John'
        result = _try_fix_truncated_json(snippet)
        assert result is not None
        parsed, fixed = result
        assert parsed == {"name": "John"}

    def test_balances_braces_outside_strings(self):
        """Should only balance structural braces outside string values."""
        from job_engine.llm import _try_fix_truncated_json

        # Truncated at the opening brace of a nested object
        snippet = '{"key": "value with { ok", "nested": {"a": 1}'
        result = _try_fix_truncated_json(snippet)
        assert result is not None
        parsed, fixed = result
        assert parsed == {"key": "value with { ok", "nested": {"a": 1}}


class TestExtractProfileFromCv:
    """Tests for extract_profile_from_cv()."""

    @patch("job_engine.llm.get_llm")
    def test_extracts_structured_profile(self, mock_get_llm):
        """Should extract structured profile data from CV text."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "name": "Jane Doe",
                "role": "Senior Python Developer",
                "experience_years": 8,
                "currency": "EUR",
                "rate": {"min_monthly": 8000, "max_monthly": 12000},
                "skills": {
                    "backend": ["python", "fastapi", "django"],
                    "databases": ["postgresql", "redis"],
                    "devops": ["docker", "aws"],
                },
                "boosted_keywords": ["python", "fastapi", "aws", "trading"],
                "experience": [
                    {"name": "FinTech Platform", "description": "Built trading engine"},
                ],
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import extract_profile_from_cv

        cv_text = "Jane Doe … 8 years of experience … Python, FastAPI …"
        result = extract_profile_from_cv(cv_text)

        assert result is not None
        assert result["name"] == "Jane Doe"
        assert result["role"] == "Senior Python Developer"
        assert result["experience_years"] == 8
        assert result["currency"] == "EUR"
        assert result["rate"]["min_monthly"] == 8000
        assert result["rate"]["max_monthly"] == 12000
        assert "backend" in result["skills"]
        assert "python" in result["skills"]["backend"]
        assert result["boosted_keywords"] == ["python", "fastapi", "aws", "trading"]

    @patch("job_engine.llm.get_llm")
    def test_uses_system_prompt_via_format_messages(self, mock_get_llm):
        """Verifies format_messages() is used so the system prompt is sent."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({"name": "Test User"})
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import extract_profile_from_cv

        result = extract_profile_from_cv("Some CV text")
        assert result is not None
        # Verify the call included a list of messages (not a plain string)
        call_arg = mock_llm.invoke.call_args[0][0]
        assert isinstance(call_arg, list), (
            f"Expected list of BaseMessages, got {type(call_arg).__name__}"
        )
        # Check the first message is a system message
        first = call_arg[0]
        assert hasattr(first, "type") or hasattr(first, "role"), (
            "First message should have a type/role attribute (BaseMessage)"
        )

    @patch("job_engine.llm.get_llm")
    def test_returns_none_when_llm_is_none(self, mock_get_llm):
        """Should return None when LLM is unavailable."""
        mock_get_llm.return_value = None

        from job_engine.llm import extract_profile_from_cv

        result = extract_profile_from_cv("Some CV text")
        assert result is None

    @patch("job_engine.llm.get_llm")
    def test_returns_none_on_parse_failure(self, mock_get_llm):
        """Should return None when LLM returns non-JSON."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Not JSON at all"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import extract_profile_from_cv

        result = extract_profile_from_cv("Some CV text")
        assert result is None


class TestImproveCv:
    """Tests for improve_cv()."""

    @patch("job_engine.llm.get_llm")
    def test_returns_improvement_result(self, mock_get_llm):
        """Should return improved CV with summary and changes."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "improved_text": "Jane Doe — Senior Python Developer...",
                "summary": "Improved action verbs and added metrics.",
                "changes": [
                    "Replaced 'was responsible for' with 'led'",
                    "Added 30% performance improvement metric",
                ],
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import improve_cv

        result = improve_cv("Jane Doe's CV text...")

        assert result is not None
        assert "improved_text" in result
        assert "summary" in result
        assert "changes" in result
        assert len(result["changes"]) == 2

    @patch("job_engine.llm.get_llm")
    def test_uses_system_prompt_via_format_messages(self, mock_get_llm):
        """Verifies format_messages() is used so the system prompt is sent."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {"improved_text": "Improved", "summary": "Ok", "changes": []}
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import improve_cv

        result = improve_cv("Some CV text")
        assert result is not None
        # Verify the call included a list of messages (not a plain string)
        call_arg = mock_llm.invoke.call_args[0][0]
        assert isinstance(call_arg, list), (
            f"Expected list of BaseMessages, got {type(call_arg).__name__}"
        )

    @patch("job_engine.llm.get_llm")
    def test_uses_profile_context_when_provided(self, mock_get_llm):
        """Should pass profile context to the LLM."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {"improved_text": "Improved", "summary": "Ok", "changes": []}
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import improve_cv

        profile = {
            "role": "Backend Developer",
            "skills": {"backend": ["python", "fastapi"]},
            "experience_years": 5,
        }
        result = improve_cv("CV text...", profile=profile)
        assert result is not None

    @patch("job_engine.llm.get_llm")
    def test_returns_none_when_llm_is_none(self, mock_get_llm):
        """Should return None when LLM is unavailable."""
        mock_get_llm.return_value = None

        from job_engine.llm import improve_cv

        result = improve_cv("Some CV text")
        assert result is None

    @patch("job_engine.llm.get_llm")
    def test_returns_none_on_parse_failure(self, mock_get_llm):
        """Should return None when LLM returns non-JSON."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Not JSON"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import improve_cv

        result = improve_cv("CV text")
        assert result is None


class TestAnalyzeJobLanguage:
    """Tests for language parameter in analyze_job()."""

    @patch("job_engine.llm.get_llm")
    def test_passes_language_instruction_to_prompt(self, mock_get_llm):
        """Should include language instruction in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({"key_skills": ["python"], "seniority": "mid"})
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import analyze_job

        analyze_job(_sample_job(), language="polish")

        # Check the prompt contains the language instruction
        call_arg = mock_llm.invoke.call_args[0][0]
        prompt_text = " ".join(getattr(m, "content", str(m)) for m in call_arg)
        assert "polish" in prompt_text.lower() or "Polish" in prompt_text


class TestExplainMatchLanguage:
    """Tests for language parameter in explain_match()."""

    @patch("job_engine.llm.get_llm")
    def test_passes_language_instruction_to_prompt(self, mock_get_llm):
        """Should include language instruction in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {"summary": "Ok", "strengths": [], "gaps": [], "recommendation": "possible"}
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import explain_match

        explain_match(_sample_job(), language="german")

        call_arg = mock_llm.invoke.call_args[0][0]
        prompt_text = " ".join(getattr(m, "content", str(m)) for m in call_arg)
        assert "german" in prompt_text.lower() or "German" in prompt_text


class TestSummarizeJobLanguage:
    """Tests for language parameter in summarize_job()."""

    @patch("job_engine.llm.get_llm")
    def test_passes_language_instruction_to_prompt(self, mock_get_llm):
        """Should include language instruction in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "A fintech company is hiring."
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import summarize_job

        summarize_job(_sample_job(), language="french")

        call_arg = mock_llm.invoke.call_args[0][0]
        prompt_text = " ".join(getattr(m, "content", str(m)) for m in call_arg)
        assert "french" in prompt_text.lower() or "French" in prompt_text


class TestCoverLetterLanguage:
    """Tests for language parameter in generate_cover_letter()."""

    @patch("job_engine.llm.get_llm")
    def test_passes_language_instruction_to_prompt(self, mock_get_llm):
        """Should include language instruction in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Letter content"
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import generate_cover_letter

        profile = {
            "role": "Backend Developer",
            "skills": {"core": ["python"]},
            "experience_years": 5,
            "language": "polish",
        }
        generate_cover_letter(_sample_job(), profile=profile, language="spanish")

        call_arg = mock_llm.invoke.call_args[0][0]
        prompt_text = " ".join(getattr(m, "content", str(m)) for m in call_arg)
        assert "spanish" in prompt_text.lower() or "Spanish" in prompt_text


class TestInterviewQuestionsLanguage:
    """Tests for language parameter in suggest_interview_questions()."""

    @patch("job_engine.llm.get_llm")
    def test_passes_language_instruction_to_prompt(self, mock_get_llm):
        """Should include language instruction in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps([{"question": "Q1", "type": "technical"}])
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import suggest_interview_questions

        suggest_interview_questions(_sample_job(), language="ukrainian")

        call_arg = mock_llm.invoke.call_args[0][0]
        prompt_text = " ".join(getattr(m, "content", str(m)) for m in call_arg)
        assert "ukrainian" in prompt_text.lower() or "Ukrainian" in prompt_text


class TestAnalyzeAllJobLanguage:
    """Tests for language parameter in analyze_all_job()."""

    @patch("job_engine.llm.get_llm")
    def test_passes_language_instruction_to_prompt(self, mock_get_llm):
        """Should include language instruction in the prompt."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "analysis": {"key_skills": ["python"], "seniority": "mid"},
                "summary": "A job.",
                "explain_match": {
                    "summary": "Ok",
                    "strengths": [],
                    "gaps": [],
                    "recommendation": "possible",
                },
                "cover_letter": "Dear...",
                "questions": ["Q1"],
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import analyze_all_job

        analyze_all_job(_sample_job(), language="polish")

        # analyze_all_job uses a plain string (not format_messages), so check invoke directly
        call_arg = mock_llm.invoke.call_args[0][0]
        assert isinstance(call_arg, str)
        assert "polish" in call_arg.lower() or "Polish" in call_arg

    @patch("job_engine.llm.get_llm")
    def test_uses_settings_language_when_no_language_arg(self, mock_get_llm):
        """Should use settings language (not profile.language) when no language arg."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "analysis": {"key_skills": ["python"], "seniority": "mid"},
                "summary": "A job.",
                "explain_match": {
                    "summary": "Ok",
                    "strengths": [],
                    "gaps": [],
                    "recommendation": "possible",
                },
                "cover_letter": "Dear...",
                "questions": ["Q1"],
            }
        )
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        from job_engine.llm import _get_settings_language, analyze_all_job

        expected = _get_settings_language().lower()
        # Profile has a "language" field, but it should be ignored — the function
        # uses the settings language (or the explicit `language` parameter) only.
        profile = {"role": "Dev", "skills": {"core": ["python"]}, "language": "german"}
        analyze_all_job(_sample_job(), profile=profile)

        call_arg = mock_llm.invoke.call_args[0][0]
        assert expected in call_arg.lower(), (
            f"Expected settings language '{expected}' in prompt, got {call_arg[:200]}"
        )
        assert "german" not in call_arg.lower(), "Profile.language should NOT be used as fallback"

    def test_returns_none_on_no_llm(self, monkeypatch):
        """Should return None when LLM unavailable, language param doesn't break."""
        from job_engine.llm import analyze_all_job

        _clear_api_key(monkeypatch)
        import job_engine.llm as llm_mod

        llm_mod._llm = None

        result = analyze_all_job(_sample_job(), language="polish")
        assert result is None

"""
LLM integration module — LangChain + OpenRouter.

Provides:
- get_llm() — cached ChatOpenAI pointing at OpenRouter
- analyze_job() — structured semantic analysis of a job post
- explain_match() — natural-language match explanation
- summarize_job() — one-paragraph job summary
- generate_cover_letter() — personalized cover letter draft
- suggest_interview_questions() — practice questions
"""

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from job_engine._prompts import (
    _COVER_LETTER_STYLE_RULES,
    _SYSTEM_PROMPT,
    ANALYSIS_PROMPT_TEMPLATE,
    APPLICATION_LETTER_HUMAN_TEMPLATE,
    COMBINED_PROMPT,
    COVER_LETTER_PROMPT_TEMPLATE,
    CV_DRAFT_PROMPT,
    CV_EXTRACTION_PROMPT,
    CV_IMPROVE_PROMPT,
    EXPLAIN_MATCH_PROMPT_TEMPLATE,
    INTERVIEW_QUESTIONS_PROMPT_TEMPLATE,
    PREP_PACK_PROMPT_TEMPLATE,
    REVIEWER_SYSTEM_PROMPT,
    SUMMARY_PROMPT_TEMPLATE,
)
from job_engine._sanitize import SANITIZE_FORBIDDANCE, sanitize_job_posting
from job_engine.config import ProfileConfig, get_app_settings
from job_engine.plugin import plugin_registry

if TYPE_CHECKING:
    from job_engine.research_budget import ResearchBudget

logger = logging.getLogger(__name__)


def _get_settings_language() -> str:
    """Read the output language from app settings, falling back to English."""
    try:
        settings = get_app_settings().load()
        return settings.get("language", "English") or "English"
    except (OSError, KeyError, TypeError, AttributeError):
        logger.warning("Failed to read settings language, falling back to English", exc_info=True)
        return "English"


def _language_instruction(language: str | None) -> str:
    """Build the standard 'write in this language' instruction line."""
    output_language = language or "English"
    return f"Write your response in {output_language}. Every part must be in that language."


def _flatten_skills(profile: dict[str, Any]) -> list[str]:
    """Flatten a profile's category-keyed skills dict into a single list."""
    all_skills: list[str] = []
    for skill_list in profile.get("skills", {}).values():
        if isinstance(skill_list, list):
            all_skills.extend(skill_list)
    return all_skills


def _import_langchain():
    """Import langchain dependencies, returning None if unavailable."""
    try:
        from langchain_core.output_parsers import PydanticOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI as _ChatOpenAI

        try:
            from langchain_anthropic import ChatAnthropic as _ChatAnthropic  # noqa: N813
        except ImportError:
            _ChatAnthropic = None  # noqa: N806

        return _ChatOpenAI, _ChatAnthropic, ChatPromptTemplate, PydanticOutputParser
    except ImportError as e:
        logger.warning("LangChain not installed: %s. LLM features will be disabled.", e)
        return None


def load_profile_files(profile: ProfileConfig | None = None) -> dict[str, str | None]:
    """Load CV, style guide, and rules files referenced by profile."""
    from job_engine._sanitize import sanitize_job_posting

    result: dict[str, str | None] = {"cv_text": None, "style_guide": None, "rules": None}
    if profile is None:
        return result
    for key, attr in [
        ("cv_text", "cv_file"),
        ("style_guide", "style_file"),
        ("rules", "rules_file"),
    ]:
        path = getattr(profile, attr)
        # The CV / style / rules files are optional user config — absent is fine
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()
            result[key] = sanitize_job_posting(content) if key == "cv_text" else content
    return result


_llm = None


def _resolve_provider() -> tuple[str, str, str]:
    """Resolve (provider, api_key, model) from app_settings.yaml.

    Supports three providers:
      - openrouter (default): ChatOpenAI pointing at OpenRouter API
      - openai:         ChatOpenAI pointing at OpenAI API directly
      - anthropic:      ChatAnthropic pointing at Anthropic API

    Reads settings from app_settings.yaml (data/app_settings.yaml), with
    fallback to environment variables for the openai/anthropic providers
    (OPENAI_API_KEY, OPENAI_MODEL, ANTHROPIC_API_KEY, ANTHROPIC_MODEL).
    """
    app_settings = get_app_settings().load()
    llm_cfg = app_settings.get("llm", {})
    provider = (llm_cfg.get("provider") or "openrouter").strip().lower()

    api_key = ""
    model = llm_cfg.get("model") or ""

    if provider == "openai":
        api_key = llm_cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
        if not model:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    elif provider == "anthropic":
        api_key = llm_cfg.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")
        if not model:
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    else:
        # Default: openrouter
        api_key = llm_cfg.get("api_key") or ""
        if not model:
            model = "openai/gpt-4o-mini"

    return provider, api_key, model


def has_api_key() -> bool:
    """Return True if an API key is configured for the current provider."""
    _, api_key, _ = _resolve_provider()
    return bool(api_key)


def get_llm():
    """Return a configured LLM instance based on app_settings.yaml.

    Returns None if the API key is not set or langchain is unavailable. Failure
    is NOT cached — if the key is added later (e.g. at runtime), the next call
    picks it up without a restart. Only a successfully built client is cached.
    """
    global _llm
    if _llm is not None:
        return _llm

    imports = _import_langchain()
    if imports is None:
        return None

    chat_openai, chat_anthropic, _, _ = imports

    provider, api_key, model = _resolve_provider()

    if provider == "anthropic" and chat_anthropic is None:
        logger.warning("langchain-anthropic not installed. Anthropic provider unavailable.")
        return None

    if not api_key:
        logger.warning(
            "LLM API key not set for provider '%s'. "
            "Set it in the dashboard Settings tab or via the corresponding env var. "
            "LLM features disabled.",
            provider,
        )
        return None

    llm_cfg = get_app_settings().load().get("llm", {})

    # Build the client
    if provider == "anthropic":
        # Guaranteed by the early return above when langchain-anthropic is missing.
        assert chat_anthropic is not None
        # kwargs dict: ChatAnthropic's pydantic field aliases (model/api key/max_tokens)
        # are not visible to static type checkers as constructor parameters.
        anthropic_kwargs: dict[str, Any] = {
            "model": model,
            "anthropic_api_key": api_key,
            "temperature": llm_cfg.get("temperature", 0.3),
            "max_tokens": llm_cfg.get("max_tokens", 8192),
            "max_retries": llm_cfg.get("max_retries", 2),
            "timeout": llm_cfg.get("request_timeout", 120),
        }
        _llm = chat_anthropic(**anthropic_kwargs)
    else:
        # OpenAI-compatible (openai or openrouter)
        kwargs: dict[str, Any] = {
            "model": model,
            "openai_api_key": api_key,
            "temperature": llm_cfg.get("temperature", 0.3),
            "max_tokens": llm_cfg.get("max_tokens", 8192),
            "max_retries": llm_cfg.get("max_retries", 2),
            "request_timeout": llm_cfg.get("request_timeout", 120),
        }
        if provider == "openrouter":
            kwargs["openai_api_base"] = "https://openrouter.ai/api/v1"
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/happydasch/job-engine",
                "X-Title": "Job Engine",
            }
        _llm = chat_openai(**kwargs)

    return _llm


def _make_job_context(job: dict[str, Any]) -> str:
    """Format a job dict into a readable context block."""
    tech = job.get("skills", [])
    if isinstance(tech, str):
        try:
            tech = json.loads(tech)
        except (json.JSONDecodeError, TypeError):
            tech = []

    lines = [
        f"Title: {sanitize_job_posting(str(job.get('title', 'N/A')))}",
        f"Company: {sanitize_job_posting(str(job.get('company', 'N/A')))}",
        f"Location: {job.get('location', 'N/A')} (Remote: {job.get('remote', False)})",
        f"Salary: {job.get('salary_min', '?')} - "
        f"{job.get('salary_max', '?')} {job.get('currency', 'USD')}",
        f"Contract: {job.get('contract_type', 'N/A')}",
        f"Experience: {job.get('experience_level', 'N/A')}",
        f"Category: {job.get('category', 'N/A')}",
        f"Tech Stack: {', '.join(tech) if tech else 'Not listed'}",
    ]

    # Use fetched_content first (full page content), fall back to scraped description
    desc = job.get("fetched_content") or job.get("description") or ""
    if desc:
        desc = sanitize_job_posting(desc)
        desc = desc[:8000]
        lines.append(f"Description: {desc}")

    return "\n".join(lines)


def _safe_invoke(llm, messages_or_str, pydantic_parser=None):
    """Invoke the LLM safely, returning (result, error) tuple.

    Args:
        llm: A ChatOpenAI instance (or None).
        messages_or_str: A list of BaseMessages (preferred), a ChatPromptTemplate,
                         or a plain string.

    Returns:
        (content_or_None, error_or_None) — error is a string key: 'no_key',
        'invocation_error', 'empty_response', or None on success.
    """
    if llm is None:
        if not has_api_key():
            return (None, "no_key")
        return (None, "invocation_error")
    try:
        if pydantic_parser:
            _input = messages_or_str | pydantic_parser
            result = _input.invoke({})
            return (result, None)
        result = llm.invoke(messages_or_str)
        content = result.content if hasattr(result, "content") else str(result)
        content = content.strip()
        if not content:
            return (None, "empty_response")
        return (content, None)
    except Exception as e:
        logger.warning("LLM invocation failed: %s", e, exc_info=True)
        return (None, "invocation_error")


def _try_fix_truncated_json(snippet: str) -> tuple[Any, str] | None:
    """Attempt to repair a truncated JSON string and parse it.

    Handles unclosed quoted strings and missing closing brackets/braces
    at the end of the snippet — the two most common LLM truncation patterns.

    Returns (parsed, fixed_text) on success, None if repair fails.
    """
    fixed = snippet.rstrip()

    # Detect and close an unclosed quoted string at the end.
    # Walk through counting unescaped double-quotes to track string state.
    in_string = False
    i = 0
    while i < len(fixed):
        c = fixed[i]
        if c == "\\":
            i += 2  # skip escaped character
            continue
        if c == '"':
            in_string = not in_string
        i += 1

    if in_string:
        fixed += '"'

    # Balance structural braces and brackets — only count those outside strings.
    open_braces = 0
    open_brackets = 0
    in_string = False
    i = 0
    while i < len(fixed):
        c = fixed[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c == "{":
                open_braces += 1
            elif c == "}":
                open_braces -= 1
            elif c == "[":
                open_brackets += 1
            elif c == "]":
                open_brackets -= 1
        i += 1

    if open_braces > 0:
        fixed += "}" * open_braces
    if open_brackets > 0:
        fixed += "]" * open_brackets

    if fixed == snippet:
        return None  # nothing was changed

    try:
        return (json.loads(fixed), fixed)
    except (json.JSONDecodeError, ValueError):
        pass

    return None


def _parse_json(text: str) -> tuple[Any, str]:
    """Parse JSON from an LLM response, tolerating markdown fences, prose,
    and truncated responses.

    Strategy: strip a ```json fence if present, try to parse; on failure fall
    back to the substring spanning the first opening bracket to the last closing
    bracket; on further failure attempt truncated-JSON recovery (closing unclosed
    strings and balancing braces/brackets).

    Returns:
        (parsed, cleaned_text) — parsed is None on failure.
    """
    if not text:
        return (None, "")

    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        return (json.loads(cleaned), cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: slice from the first { or [ to the last } or ].
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if starts:
        start = min(starts)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if end > start:
            snippet = cleaned[start : end + 1]
            try:
                return (json.loads(snippet), snippet)
            except (json.JSONDecodeError, ValueError):
                pass
        else:
            # No closing bracket found — try the whole substring from start
            snippet = cleaned[start:]
            recovered = _try_fix_truncated_json(snippet)
            if recovered:
                return recovered

    # Last resort: try truncated-JSON recovery on the full cleaned text
    recovered = _try_fix_truncated_json(cleaned)
    if recovered:
        return recovered

    return (None, cleaned)


def analyze_job(job: dict[str, Any], language: str | None = None) -> dict[str, Any] | None:
    """Return structured analysis of a job post, or None on failure.

    Returns a dict with keys: key_skills, nice_to_have, seniority,
    responsibilities, skills_inferred, red_flags, relevance_notes.

    Args:
        job: Job posting dict.
        language: Output language (e.g. 'english', 'polish'). Defaults to 'english'.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_id = job.get("id") if isinstance(job, dict) else None
    plugin_registry.trigger(
        "on_analysis_start",
        job_id,
        {"role": job.get("title"), "company": job.get("company")},
    )

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", ANALYSIS_PROMPT_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            job_context=job_context,
            language_instruction=language_instruction,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if result is None:
        plugin_registry.trigger("on_analysis_complete", job_id, None)
        return None

    parsed, _ = _parse_json(result)
    if parsed is None:
        logger.warning(
            "Failed to parse LLM analysis JSON (%d chars) | head=%r | tail=%r",
            len(result),
            result[:150],
            result[-250:],
        )
    plugin_registry.trigger("on_analysis_complete", job_id, parsed)
    return parsed


def explain_match(
    job: dict[str, Any],
    match_details: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    """Return a natural-language match explanation.

    Returns a dict with keys: summary, strengths, gaps, recommendation.

    Args:
        job: Job posting dict.
        match_details: Match scoring breakdown (optional).
        language: Output language (e.g. 'english', 'polish'). Defaults to 'english'.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language)

    profile_notes = ""
    if match_details:
        components = match_details.get("components", {})
        if components:
            profile_notes = "Match components:\n" + "\n".join(
                f"  {k}: {v['score']}/100 (weight: {v['weight'] * 100:.0f}%)"
                for k, v in components.items()
            )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", EXPLAIN_MATCH_PROMPT_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            job_context=job_context,
            profile_notes=profile_notes,
            language_instruction=language_instruction,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if result is None:
        return None

    parsed, _ = _parse_json(result)
    if parsed is None:
        logger.warning(
            "Failed to parse LLM explanation JSON (%d chars) | head=%r | tail=%r",
            len(result),
            result[:150],
            result[-250:],
        )
    return parsed


def summarize_job(job: dict[str, Any], language: str | None = None) -> str | None:
    """Return a one-paragraph summary of the job for card display.

    Args:
        job: Job posting dict.
        language: Output language (e.g. 'english', 'polish'). Defaults to 'english'.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", SUMMARY_PROMPT_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            job_context=job_context,
            language_instruction=language_instruction,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    return result


def generate_cover_letter(
    job: dict[str, Any],
    profile: dict[str, Any] | None = None,
    language: str | None = None,
    review: bool = False,
    ats_verify: bool = False,
) -> str | None:
    """Generate a personalized cover letter for this job.

    Args:
        job: Job posting dict.
        profile: Candidate profile (optional).
        language: Output language (e.g. 'english', 'polish'). Overrides profile.
        review: When True, run a second LLM review pass to catch issues.
        ats_verify: When True, run ATS compatibility checks on the output.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language or _get_settings_language())

    profile_context = ""
    candidate_name = "the candidate"
    if profile:
        candidate_name = profile.get("name", "the candidate")
        all_skills = _flatten_skills(profile)
        projects = profile.get("experience", []) or profile.get("projects", [])
        profile_currency = profile.get("rate", {}).get("currency") or profile.get("currency", "USD")
        profile_context = (
            f"Candidate role: {profile.get('role', 'Not specified')}\n"
            f"Skills: {', '.join(all_skills)}\n"
            f"Experience: {profile.get('experience_years', 'N/A')} years\n"
            f"Rate: {profile.get('rate', {}).get('min_monthly', 'N/A')} - "
            f"{profile.get('rate', {}).get('max_monthly', 'N/A')} {profile_currency}\n"
            f"Output language: {profile.get('language', 'English')}\n"
        )
        if projects:
            profile_context += "Key projects:\n" + "\n".join(
                f"  - {p.get('name', '')}: {p.get('description', '')}" for p in projects[:3]
            )

    # Load CV, style, and rules from profile split files
    _profile_split = ProfileConfig()
    cv_content = _profile_split.load_cv()
    style_content = _profile_split.load_style()
    rules_content = _profile_split.load_rules()
    if cv_content:
        profile_context += f"\nCV:\n{cv_content}\n"
    if style_content:
        profile_context += f"\nWriting Style:\n{style_content}\n"
    if rules_content:
        profile_context += f"\nRules:\n{rules_content}\n"

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are the candidate applying for this job. "
                "Write a cover letter in first person, as yourself. "
                "You skip fluff, you name specific systems, "
                + "and you show exactly how your past work maps to their problems.\n"
                + _COVER_LETTER_STYLE_RULES
                + "\n\nCandidate name: {candidate_name}",
            ),
            ("human", COVER_LETTER_PROMPT_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            candidate_name=candidate_name,
            job_context=job_context,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
            profile_context=profile_context,
            language_instruction=language_instruction,
        ),
    )
    if result is None:
        return None

    # Optional drafter-reviewer pass
    if review:
        review_result = review_cover_letter(result, job, profile)
        if review_result.get("reviewed"):
            result = review_result["revised_text"]

    # Optional ATS verification
    if ats_verify:
        ats_result = verify_ats_compatibility(result, job)
        if not ats_result.get("overall_ok", True):
            logger.info(
                "ATS check: word_count_ok=%s, has_contact=%s, no_markdown=%s, "
                "keyword_coverage=%.1f%%",
                ats_result.get("word_count_ok"),
                ats_result.get("has_contact"),
                ats_result.get("no_markdown"),
                ats_result.get("keyword_coverage_pct", 0),
            )

    return result


def review_cover_letter(
    draft: str, job: dict, profile: dict | None = None, language: str | None = None
) -> dict:
    """Review a cover letter draft for issues, then return a revised version.

    Runs a second LLM pass with fresh context (drafter-reviewer pattern).
    Returns dict with keys: reviewed (bool), revised_text (str), issues (list).
    ``reviewed`` is False when the review call failed and the draft is returned unchanged.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    job_context = _make_job_context(job)
    output_language = language or _get_settings_language()

    review_prompt = f"""{SANITIZE_FORBIDDANCE}

Review this cover letter draft for:
1. Hallucinated facts (skills, companies, roles not in the job posting or candidate's CV)
2. Tone mismatches vs standard cover letter conventions
3. Factual errors or inconsistencies
4. Missing key requirements from the job posting

Then output ONLY the revised letter text in {output_language}, with the corrections applied.
No preamble, no list of issues, no commentary.

<draft>
{sanitize_job_posting(draft)}
</draft>

<job_posting>
{job_context}
</job_posting>"""

    llm = get_llm()
    result, error = _safe_invoke(
        llm, [SystemMessage(content=REVIEWER_SYSTEM_PROMPT), HumanMessage(content=review_prompt)]
    )
    if error or not result:
        logger.warning("Cover letter review failed (%s); keeping unreviewed draft", error)
        return {"reviewed": False, "revised_text": draft, "issues": []}

    return {"reviewed": True, "revised_text": result.strip(), "issues": []}


def verify_ats_compatibility(letter_text: str, job: dict) -> dict:
    """Verify a cover letter for ATS compatibility.

    Checks: word count, keyword coverage, contact details, plain text format.
    Returns dict with scores and recommendations.
    """
    word_count = len(letter_text.split())
    checks = {
        "word_count": word_count,
        "word_count_ok": 200 <= word_count <= 500,
        "has_contact": any(p in letter_text for p in ["@", "linkedin", "github", "portfolio"]),
        "no_markdown": not any(m in letter_text for m in ["**", "##", "```", "###"]),
    }

    # Check keyword coverage from job
    job_text = (job.get("description") or "") + " " + (job.get("title") or "")
    key_terms = {w.lower() for w in job_text.split() if len(w) > 3 and w.isalpha()}
    letter_words = {w.lower() for w in letter_text.split()}
    covered = key_terms & letter_words
    coverage = len(covered) / max(len(key_terms), 1) * 100 if key_terms else 0

    checks["keyword_coverage_pct"] = round(coverage, 1)
    checks["keywords_matched"] = sorted(covered)
    checks["overall_ok"] = (
        checks["word_count_ok"] and checks["has_contact"] and checks["no_markdown"]
    )

    return checks


def suggest_interview_questions(
    job: dict[str, Any], language: str | None = None
) -> list[dict[str, Any]] | None:
    """Return a list of practice interview questions based on the job requirements.

    Each question is a dict with keys: question, type, prep_tip, star.
    star (behavioral only): an object with keys situation, task, action, result.
    Types: 'technical', 'behavioral', 'problem_solving', 'career'.

    Args:
        job: Job posting dict.
        language: Output language (e.g. 'english', 'polish'). Defaults to 'english'.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", INTERVIEW_QUESTIONS_PROMPT_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            job_context=job_context,
            language_instruction=language_instruction,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if result is None:
        return None

    parsed, _ = _parse_json(result)
    if not isinstance(parsed, list):
        logger.warning(
            "Failed to parse interview questions JSON (%d chars) | head=%r | tail=%r",
            len(result),
            result[:150],
            result[-250:],
        )
        return None
    return parsed


def generate_interview_prep_pack(
    job: dict[str, Any],
    stage: str = "phone_screen",
    cv_text: str = "",
    cover_letter_text: str = "",
    language: str | None = None,
) -> dict[str, Any] | None:
    """Generate a stage-specific interview preparation pack.

    Combines the job posting, CV, and cover letter into a structured
    prep pack with likely questions, STAR mapping, company research,
    and a consistency brief.

    Args:
        job: Job posting dict.
        stage: Interview stage name (phone_screen, technical, onsite, final).
        cv_text: The candidate's CV text.
        cover_letter_text: The candidate's cover letter for this application.
        language: Output language (e.g. 'english', 'polish').

    Returns:
        A dict with keys: stage, likely_questions, star_mapping,
        company_research, consistency_brief. Returns None on failure.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language)
    cv_context = cv_text[:2000] if cv_text else "No CV available."
    cl_text = cover_letter_text[:1500] if cover_letter_text else "No cover letter available."

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", PREP_PACK_PROMPT_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            stage=stage,
            job_context=job_context,
            cv_context=cv_context,
            cover_letter_text=cl_text,
            language_instruction=language_instruction,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if result is None:
        logger.warning("Interview prep pack generation failed: %s", error)
        return None

    parsed, parse_error = _parse_json(result)
    if not isinstance(parsed, dict):
        logger.warning(
            "Failed to parse prep pack JSON (%d chars) | error=%s | head=%r",
            len(result),
            parse_error,
            result[:200],
        )
        return None
    return parsed


def generate_application_letter(
    job: dict[str, Any],
    profile: dict[str, Any] | None = None,
    language: str | None = None,
    style: str | None = None,
    tone: str | None = None,
    length: str | None = None,
    draft: str | None = None,
) -> str | None:
    """Generate a fresh application letter with configurable settings.

    Unlike ``generate_cover_letter`` (which is a fixed-style cover letter
    produced as part of the combined analysis), this function creates a
    standalone application letter from scratch, respecting the user's
    chosen language, style, tone, and length preferences.

    Args:
        job: Job posting dict.
        profile: Candidate profile dict (optional).
        language: Output language (e.g. 'english', 'polish'). Overrides profile.
        style: Writing style — 'professional', 'concise', 'detailed', 'enthusiastic'.
        tone: Voice tone — 'formal', 'neutral', 'warm', 'confident'.
        length: Desired length — 'short', 'medium', 'long'.
        draft: Optional existing draft text (from analysis) used as context only.
            The function writes a fresh letter — it does not edit the draft.

    Returns:
        The letter text as a string, or None on failure.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)

    # Determine language
    output_language = language or _get_settings_language()

    # Normalise settings
    style = (style or "professional").lower()
    tone = (tone or "neutral").lower()
    length = (length or "medium").lower()

    # Build style instruction block
    style_guide = {
        "professional": (
            "Write a polished, standard business letter. "
            "Clear structure, measured tone, concrete examples. "
            "Aim for credibility and competence."
        ),
        "concise": (
            "Write a short, punchy letter. Every sentence must earn its place. "
            "No filler, no repetition. Get straight to the point."
        ),
        "detailed": (
            "Write a thorough letter. Include specific project details, "
            "metrics, and technical context. Show deep expertise."
        ),
        "enthusiastic": (
            "Write with genuine energy and interest. Show excitement about "
            "the company's mission and the role. Keep it professional but warm."
        ),
    }
    tone_guide = {
        "formal": (
            "Use formal business language. Avoid contractions. "
            "Address the reader as if writing to a senior executive."
        ),
        "neutral": ("Use a balanced, professional tone. Direct and straightforward."),
        "warm": (
            "Write with a friendly, approachable voice. Use natural language that builds rapport."
        ),
        "confident": (
            "Write with assertive confidence. Use strong verbs and "
            "declarative statements. Own your accomplishments."
        ),
    }
    length_guide = {
        "short": "Keep the letter very brief — 3 to 4 paragraphs, max 250 words.",
        "medium": "Write a standard letter — 4 to 5 paragraphs, max 500 words.",
        "long": "Write a detailed letter — 6 to 7 paragraphs, max 1000 words.",
    }

    style_instruction = style_guide.get(style, style_guide["professional"])
    tone_instruction = tone_guide.get(tone, tone_guide["neutral"])
    length_instruction = length_guide.get(length, length_guide["medium"])

    profile_context = ""
    candidate_name = "the candidate"
    if profile:
        candidate_name = profile.get("name", "the candidate")
        all_skills = _flatten_skills(profile)
        projects = profile.get("experience", []) or profile.get("projects", [])
        profile_context = (
            f"Candidate role: {profile.get('role', 'Not specified')}\n"
            f"Skills: {', '.join(all_skills)}\n"
            f"Experience: {profile.get('experience_years', 'N/A')} years\n"
        )
        if projects:
            profile_context += "Key projects:\n" + "\n".join(
                f"  - {p.get('name', '')}: {p.get('description', '')}" for p in projects[:3]
            )

    draft_block = ""
    if draft:
        draft_block = f"\nReference draft (use for context only — do NOT copy verbatim):\n{draft}\n"

    # Load CV, style, and rules from profile split files
    _profile_split = ProfileConfig()
    cv_content = _profile_split.load_cv()
    style_content = _profile_split.load_style()
    rules_content = _profile_split.load_rules()
    if cv_content:
        profile_context += f"\nCV:\n{cv_content}\n"
    if style_content:
        profile_context += f"\nWriting Style:\n{style_content}\n"
    if rules_content:
        profile_context += f"\nRules:\n{rules_content}\n"

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are the candidate applying for this job. "
                "Write a professional application letter in first person, as yourself. "
                "You skip fluff, you name specific systems, "
                "and you show exactly how your past work maps to their problems.\n"
                + _COVER_LETTER_STYLE_RULES
                + "\n\nCandidate name: {candidate_name}\n"
                f"Output language: {output_language}\n"
                "IMPORTANT: Write the ENTIRE letter in the output language specified above. "
                "Every paragraph, every sentence must be in that language.",
            ),
            ("human", APPLICATION_LETTER_HUMAN_TEMPLATE),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            candidate_name=candidate_name,
            job_context=job_context,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
            profile_context=profile_context,
            draft_block=draft_block,
            style=style,
            style_instruction=style_instruction,
            tone=tone,
            tone_instruction=tone_instruction,
            length=length,
            length_instruction=length_instruction,
            output_language=output_language,
        ),
    )
    return result


def _make_match_context(job: dict[str, Any]) -> str:
    """Format match details into a readable context string."""
    match_details = job.get("match_details") or {}
    components = match_details.get("components", {})
    if not components:
        return "Match scoring not available."
    lines = ["Match score breakdown:"]
    for k, v in components.items():
        lines.append(f"  {k}: {v.get('score', '?')}/100 (weight: {v.get('weight', 0) * 100:.0f}%)")
    return "\n".join(lines)


def _make_profile_context(profile: dict[str, Any] | None) -> str:
    """Format a candidate profile into a readable context string."""
    if not profile:
        return "Candidate profile not provided."
    all_skills = _flatten_skills(profile)
    projects = profile.get("experience", []) or profile.get("projects", [])
    profile_currency = (
        profile.get("rate", {}).get("currency") or profile.get("currency") or "USD"
    ).upper()
    lines = [
        f"Candidate role: {profile.get('role', 'Not specified')}",
        f"Skills: {', '.join(all_skills)}",
        f"Experience: {profile.get('experience_years', 'N/A')} years",
        f"Rate: {profile.get('rate', {}).get('min_monthly', 'N/A')} - "
        f"{profile.get('rate', {}).get('max_monthly', 'N/A')} {profile_currency}",
    ]

    # Include language preference
    settings_lang = _get_settings_language()
    if settings_lang:
        lines.append(f"Output language: {settings_lang}")
    candidate_languages = profile.get("languages")
    if candidate_languages:
        if isinstance(candidate_languages, list):
            lang_str = ", ".join(
                (
                    f"{lang.get('name', lang.get('code', lang))} ({lang.get('level', '')})"
                    if isinstance(lang, dict)
                    else str(lang)
                )
                for lang in candidate_languages
            )
            lines.append(f"Languages: {lang_str}")

    if projects:
        lines.append("Key projects:")
        for p in projects[:3]:
            lines.append(f"  - {p.get('name', '')}: {p.get('description', '')}")
    return "\n".join(lines)


def analyze_all_job(
    job: dict[str, Any],
    profile: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    """Return combined LLM analysis in a single request.

    Produces a dict with keys: analysis, summary, explain_match,
    cover_letter, questions — all from one LLM invocation.

    Args:
        job: Job posting dict.
        profile: Candidate profile (optional).
        language: Output language (e.g. 'english', 'polish'). Overrides profile.

    Returns None on failure (no key, invocation error, or parse failure).
    """
    llm = get_llm()
    if llm is None:
        return None

    job_context = _make_job_context(job)
    profile_context = _make_profile_context(profile)
    match_notes = _make_match_context(job)

    output_language = language or _get_settings_language()
    language_instruction = (
        f"Write the ENTIRE response in {output_language}. "
        f"Every section, every sentence must be in that language. "
        f"Language: {output_language}."
    )

    prompt = COMBINED_PROMPT.format(
        job_context=job_context,
        profile_context=profile_context,
        match_notes=match_notes,
        language_instruction=language_instruction,
        SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
    )

    result, error = _safe_invoke(llm, prompt)
    if result is None:
        return None

    parsed, _ = _parse_json(result)
    if parsed is None or not isinstance(parsed, dict):
        logger.warning(
            "Failed to parse combined LLM response (%d chars) | head=%r | tail=%r",
            len(result),
            result[:200],
            result[-300:],
        )
        return None

    # Validate expected keys (warn about missing, don't fail)
    expected = {"analysis", "summary", "explain_match", "cover_letter", "questions"}
    missing = expected - set(parsed.keys())
    if missing:
        logger.warning(
            "Combined LLM response missing keys: %s. Response had: %s",
            missing,
            list(parsed.keys()),
        )

    return parsed


# ── CV Profile Extraction ───────────────────────────────────────────────────


def extract_profile_from_cv(cv_text: str) -> dict[str, Any] | None:
    """Extract structured profile data from a CV/resume text using the LLM.

    Returns a dict with keys: name, role, experience_years, currency, rate,
    skills, boosted_keywords, experience.

    Returns None if the LLM is unavailable or the response cannot be parsed.
    """
    llm = get_llm()
    if llm is None:
        logger.warning("LLM unavailable for CV extraction (no API key or langchain)")
        return None

    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CV_EXTRACTION_PROMPT),
            ("human", "{SANITIZE_FORBIDDANCE}\n\nHere is the CV text:\n\n{cv_text}"),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            cv_text=sanitize_job_posting(cv_text[:15000]),
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if error or result is None:
        logger.warning("CV extraction LLM call failed: %s", error)
        return None

    parsed, _ = _parse_json(result)
    if parsed is None or not isinstance(parsed, dict):
        logger.warning(
            "Failed to parse CV extraction result (%d chars) | head=%r",
            len(result or ""),
            (result or "")[:200],
        )
        return None

    return parsed


# ── CV Improvement ────────────────────────────────────────────────────────────


def improve_cv(cv_text: str, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Improve a CV/resume text using the LLM.

    Takes the raw CV text and an optional profile, returns a dict with keys:
    ``improved_text``, ``summary``, and ``changes``.

    Returns None if the LLM is unavailable or the response cannot be parsed.
    """
    llm = get_llm()
    if llm is None:
        logger.warning("LLM unavailable for CV improvement (no API key or langchain)")
        return None

    from langchain_core.prompts import ChatPromptTemplate

    profile_context = _make_profile_context(profile) if profile else "No profile provided."

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CV_IMPROVE_PROMPT),
            (
                "human",
                "{SANITIZE_FORBIDDANCE}\n\n"
                "Candidate profile context:\n{profile_context}\n\n"
                "Current CV text:\n{cv_text}",
            ),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            cv_text=sanitize_job_posting(cv_text[:15000]),
            profile_context=profile_context,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if error or result is None:
        logger.warning("CV improvement LLM call failed: %s", error)
        return None

    parsed, _ = _parse_json(result)
    if parsed is None or not isinstance(parsed, dict):
        logger.warning(
            "Failed to parse CV improvement result (%d chars) | head=%r",
            len(result or ""),
            (result or "")[:200],
        )
        return None

    return parsed


# ── Research Budget ────────────────────────────────────────────────────────────


def get_research_budget() -> "ResearchBudget":
    """Get a ResearchBudget instance based on current settings."""
    from job_engine.research_budget import get_research_budget_from_settings

    return get_research_budget_from_settings()


# ── Reports ────────────────────────────────────────────────────────────────────


def save_analysis_report(job_id: int, analysis_data: dict) -> str | None:
    """Save analysis as a numbered report."""
    try:
        from job_engine.reports import save_report

        return save_report(job_id, analysis_data)
    except Exception as exc:
        logger.warning("Failed to save analysis report: %s", exc)
        return None


# ── CV Generation ──────────────────────────────────────────────────────────


def generate_cv(
    job: dict[str, Any],
    profile: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    """Generate a job-tailored CV in LaTeX format (CV drafter agent).

    Uses the CV_DRAFT_PROMPT to produce a complete moderncv LaTeX document
    addressing every requirement from the job posting.

    Args:
        job: Job posting dict.
        profile: Candidate profile dict (optional — falls back to ProfileConfig).
        language: Output language override.

    Returns:
        Dict with keys: cv_latex (str), skills_covered (list), skills_gapped (list),
        nice_to_haves_engaged (list), summary (str). None on failure.
    """
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_llm()
    if llm is None:
        return None

    # Load profile
    if profile is None:
        profile = ProfileConfig().load()

    job_context = _make_job_context(job)
    language_instruction = _language_instruction(language or _get_settings_language())

    # Build profile context
    profile_context = _make_profile_context(profile)
    candidate_name = profile.get("name", "the candidate")

    # Load CV text if available (for LLM to reference existing content)
    cv_text_block = ""
    cv_text = ProfileConfig().load_cv()
    if cv_text:
        cv_text_block = f"\n## Candidate's current CV text (for reference)\n{cv_text}\n"

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a senior CV writer preparing a job-tailored LaTeX CV. "
                "You write in moderncv banking style. Every requirement from the "
                "job posting must be addressed. "
                "Your output must be valid JSON. Candidate name: {candidate_name}",
            ),
            ("human", CV_DRAFT_PROMPT),
        ]
    )

    result, error = _safe_invoke(
        llm,
        prompt.format_messages(
            candidate_name=candidate_name,
            job_context=job_context,
            profile_context=profile_context,
            cv_text_block=cv_text_block,
            language_instruction=language_instruction,
            SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
        ),
    )
    if result is None:
        return None

    parsed, _ = _parse_json(result)
    if parsed is None:
        logger.warning("generate_cv: failed to parse LLM JSON output")
        return None

    # Trim CV if it's too long for 2 pages (optional post-processing)
    cv_latex = parsed.get("cv_latex", "")
    if cv_latex:
        trimmed = _trim_cv_to_fit(cv_latex)
        parsed["cv_latex"] = trimmed

    return parsed


def _trim_cv_to_fit(cv_latex: str, max_lines: int = 45) -> str:
    """Trim a CV LaTeX source to approximately fit 2 pages.

    Uses heuristic line counting — removes low-value lines (bullet points
    that are generic or filler) until the body is under ``max_lines``.

    This is a heuristic pre-compilation trim. The actual 2-page check
    happens via verify_cv() after compilation.

    Args:
        cv_latex: The CV LaTeX source.
        max_lines: Maximum target lines of body content. Defaults to 45
                   (roughly 2 pages of moderncv).

    Returns:
        Trimmed LaTeX source.
    """
    if not cv_latex:
        return cv_latex

    lines = cv_latex.split("\n")

    # Count total body lines (excluding preamble and document boundaries)
    body_start = 0
    body_end = len(lines)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == r"\begin{document}":
            body_start = i + 1
        if stripped == r"\end{document}":
            body_end = i
            break

    body_lines = lines[body_start:body_end]

    if len(body_lines) <= max_lines:
        return cv_latex  # No trimming needed

    # Count how many lines to remove
    to_remove = len(body_lines) - max_lines

    # Identify low-value items: \item lines that are short, generic, or filler
    low_value_indices = []
    for idx, line in enumerate(body_lines):
        stripped = line.strip()
        # Flag short generic bullets
        if r"\item" in stripped and len(stripped) < 40:
            low_value_indices.append(idx)
        # Flag empty cvitem
        if r"\cvitem" in stripped and stripped.rstrip().endswith("{}"):
            low_value_indices.append(idx)

    # Remove low-value items (from end of list to preserve indices)
    removed = 0
    for idx in sorted(low_value_indices, reverse=True):
        if removed >= to_remove:
            break
        body_lines.pop(idx)
        removed += 1

    # If still too long, remove from the end of the experience section
    if len(body_lines) > max_lines:
        # Find \cventry blocks and remove trailing bullets
        excess = len(body_lines) - max_lines
        for idx in range(len(body_lines) - 1, -1, -1):
            if excess <= 0:
                break
            stripped = body_lines[idx].strip()
            if r"\item" in stripped:
                body_lines.pop(idx)
                excess -= 1

    return (
        "\n".join(lines[:body_start])
        + "\n"
        + "\n".join(body_lines)
        + "\n"
        + "\n".join(lines[body_end:])
    )

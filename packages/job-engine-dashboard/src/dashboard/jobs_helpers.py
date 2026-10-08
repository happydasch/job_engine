"""Shared helpers for job-related routes — filtering, sorting, LLM caching.

Eliminates the ~80 lines of duplicated filter/sort logic between the
HTML and JSON job-list endpoints, and the ~25 lines of duplicated LLM
cache-save block across the four LLM endpoints plus fetch_content.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from job_engine.database import get_sync_engine as get_engine
from job_engine.models import Job
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job filtering & sorting
# ---------------------------------------------------------------------------


def filter_and_sort_jobs(
    jobs: list[dict],
    *,
    q: str = "",
    sort_by: str = "match_score",
    sort_order: str = "desc",
    min_score: float = 0.0,
    platform: str = "",
    remote: str = "",
    show_hidden: str = "",
    hidden_only: str = "",
    show_favorites: str = "",
    show_applied: str = "",
    show_enriched: str = "",
    skill: str = "",
    location: str = "",
    experience_level: str = "",
    category: str = "",
    contract_type: str = "",
) -> list[dict]:
    """Apply all filter parameters and sort to a list of job dicts.

    Mirrors the query-parameter contract of ``api_jobs()`` (JSON) — any
    parameter omitted or left at its default is a no-op.

    Sorting rules:
    - ``sort_order`` controls direction: ``\"desc\"`` (default) or ``\"asc\"``.
    - ``favorite`` sorts favorited jobs first (order-independent — the label
      promises a group, not a direction).
    - ``application`` sorts applied jobs first (likewise order-independent).
    - Nulls sort last regardless of field type.
    """
    # ── Filters ──────────────────────────────────────────────────────────────
    if hidden_only == "true":
        jobs = [j for j in jobs if j.get("hidden", False)]
    elif show_hidden != "true":
        jobs = [j for j in jobs if not j.get("hidden", False)]

    if show_favorites == "true":
        jobs = [j for j in jobs if j.get("favorite", False)]

    if show_applied == "true":
        jobs = [j for j in jobs if j.get("application_status") is not None]

    if show_enriched == "true":
        jobs = [
            j for j in jobs if j.get("llm_analysis") and j["llm_analysis"] not in ("", "{}", "null")
        ]

    if q:
        q_lower = q.lower()
        text_fields = ("title", "company", "location", "contract_type", "description")
        jobs = [
            j
            for j in jobs
            if any(q_lower in (j.get(f) or "").lower() for f in text_fields)
            or any(q_lower in s.lower() for s in j.get("skills", []))
        ]

    if min_score > 0:
        jobs = [j for j in jobs if (j.get("match_score") or 0) >= min_score]

    if platform:
        platform_lower = platform.lower()
        jobs = [j for j in jobs if j.get("platform", "").lower() == platform_lower]

    if remote:
        is_remote = remote == "true"
        jobs = [
            j
            for j in jobs
            if j.get("remote", False) == is_remote
            or (is_remote and "remote" in (j.get("location") or "").lower())
        ]

    if skill:
        # Normalize the filter skill the same way normalize_skill() in skill_scorer.py does
        from job_engine.skill_scorer import normalize_skill as _norm_skill

        normalized = _norm_skill(skill)
        jobs = [j for j in jobs if any(normalized == _norm_skill(s) for s in j.get("skills", []))]

    if location:
        location_lower = location.lower()
        jobs = [j for j in jobs if location_lower in (j.get("location") or "").lower()]

    if experience_level:
        selected = {lvl.strip().lower() for lvl in experience_level.split(",") if lvl.strip()}
        jobs = [j for j in jobs if j.get("experience_level", "").lower() in selected]

    if category:
        category_lower = category.lower()
        jobs = [j for j in jobs if j.get("category", "").lower() == category_lower]

    if contract_type:
        selected = {ct.strip().lower() for ct in contract_type.split(",") if ct.strip()}
        jobs = [j for j in jobs if j.get("contract_type", "").lower() in selected]

    # ── Sort ─────────────────────────────────────────────────────────────────
    reverse = sort_order == "desc"

    def _sort_key(job: dict) -> tuple:
        if sort_by == "favorite":
            return (0, 0 if job.get("favorite", False) else 1)
        if sort_by == "application":
            return (0, 0 if job.get("application_status") is not None else 1)
        v = job.get(sort_by)
        if v is None:
            return (1, "")
        if isinstance(v, (int, float)):
            return (0, v)
        if isinstance(v, str):
            return (1, v.lower())
        return (1, str(v))

    # "Favs First" / "Applied First" describe a group order, not a direction —
    # reversing them would put the "first" group last under the default desc.
    if sort_by in ("favorite", "application"):
        jobs.sort(key=_sort_key)
        return jobs

    jobs.sort(key=_sort_key, reverse=reverse)
    return jobs


def collect_available_platforms(jobs: list[dict]) -> list[str]:
    """Return a sorted list of unique platform names from the given jobs."""
    return sorted(set(j.get("platform", "") for j in jobs))


def collect_available_skills(jobs: list[dict]) -> list[str]:
    """Return a sorted list of unique skill names from the given jobs."""
    skills_set: set[str] = set()
    for j in jobs:
        for s in j.get("skills", []):
            skills_set.add(s)
    return sorted(skills_set)


def collect_available_locations(jobs: list[dict]) -> list[str]:
    """Return a sorted list of unique non-empty locations from the given jobs."""
    return sorted(set(j.get("location", "") for j in jobs if j.get("location")))


def collect_available_experience_levels(jobs: list[dict]) -> list[str]:
    """Return a sorted list of unique non-empty experience levels from the given jobs."""
    return sorted(set(j.get("experience_level", "") for j in jobs if j.get("experience_level")))


def collect_available_categories(jobs: list[dict]) -> list[str]:
    """Return a sorted list of unique non-empty categories from the given jobs."""
    return sorted(set(j.get("category", "") for j in jobs if j.get("category")))


def collect_available_contract_types(jobs: list[dict]) -> list[str]:
    """Return a sorted list of unique non-empty contract types from the given jobs."""
    return sorted(set(j.get("contract_type", "") for j in jobs if j.get("contract_type")))


# ---------------------------------------------------------------------------
# LLM cache helpers
# ---------------------------------------------------------------------------


def _save_llm_fields_to_job(job_id: str, combined: dict[str, Any]) -> None:
    """Persist all LLM result fields from a combined analysis to the DB.

    Writes ``llm_analysis``, ``llm_explain_match``, ``llm_cover_letter``,
    and ``llm_questions`` in a single short-lived session, handling the
    ``summary`` merge into the analysis dict.
    """
    engine = get_engine()
    with Session(engine) as session:
        db_job = session.query(Job).filter(Job.external_id == job_id).first()
        if db_job is None:
            return

        # Analysis + summary merge
        analysis = combined.get("analysis")
        summary = combined.get("summary")
        if analysis:
            if summary:
                analysis = {**analysis, "summary": summary}
            db_job.llm_analysis = json.dumps(analysis)

        explain = combined.get("explain_match")
        if explain:
            db_job.llm_explain_match = json.dumps(explain)

        letter = combined.get("cover_letter")
        if letter:
            db_job.llm_cover_letter = letter

        qs = combined.get("questions")
        if qs:
            db_job.llm_questions = json.dumps(qs)

        db_job.updated_at = datetime.now(UTC)
        session.commit()


def _extract_llm_field(job: Job, field: str):
    """Safely extract a JSON or text LLM field from a Job ORM row.

    Handles ``llm_analysis``, ``llm_explain_match``, ``llm_questions``
    (JSON columns) and ``llm_cover_letter`` (plain text).
    """
    val = getattr(job, field)
    if val is None:
        return None
    if field == "llm_cover_letter":
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupt %s JSON for job %s — ignoring", field, job.external_id)
        return None

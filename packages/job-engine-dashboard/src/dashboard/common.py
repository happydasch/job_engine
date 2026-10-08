"""Shared state and utilities for the API dashboard route modules.

Provides DB/scoring loaders, job helpers, and scraper utilities.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from job_engine.config import get_profile_config
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import Company, Job
from job_engine.skill_scorer import JobMatcher, score_all_jobs
from sqlalchemy.orm import Session, joinedload

# ---------------------------------------------------------------------------
# Project root & env
# ---------------------------------------------------------------------------

_root = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(_root / "config" / ".env")

# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def job_to_dict(job: Job) -> dict:
    """Convert a Job ORM model to a dict. Delegates to Job.to_dict()."""
    return job.to_dict()


def load_jobs_from_db() -> list[dict]:
    """Load all jobs from the database and return as dicts."""
    engine = get_engine()
    with Session(engine) as session:
        db_jobs = (
            session.query(Job)
            .options(joinedload(Job.company_rel), joinedload(Job.applications))
            .order_by(Job.updated_at.desc())
            .all()
        )
        return [job_to_dict(j) for j in db_jobs]


def get_scored_jobs() -> list[dict[str, Any]]:
    """Load jobs and score them against the profile.

    Results are cached with a short TTL (default 30s) so that the 3+ API
    calls per page load (stats, jobs listing, skills) don't each re-score
    all 870 jobs independently.
    """
    global _scored_cache
    now = time.monotonic()
    if _scored_cache is not None and (now - _scored_cache["ts"]) < SCORED_CACHE_TTL:
        return _scored_cache["jobs"]

    jobs = load_jobs_from_db()
    if not jobs:
        _scored_cache = {"ts": now, "jobs": []}
        return []
    scored = score_all_jobs(jobs, matcher=_get_matcher())
    _scored_cache = {"ts": now, "jobs": scored}
    return scored


# Cache the matcher so per-job scoring doesn't re-parse the profile YAML each call.
_matcher: JobMatcher | None = None
_scored_cache: dict | None = None  # {"ts": float, "jobs": list[dict]}
SCORED_CACHE_TTL = 30  # seconds — short enough to stay fresh across page loads


def invalidate_scored_cache() -> None:
    """Drop the scored-jobs cache so the next request re-reads the DB.

    Called after writes that the list filters key off (favorite/hidden), which
    would otherwise be invisible for up to ``SCORED_CACHE_TTL`` seconds.
    """
    global _scored_cache
    _scored_cache = None


def _get_matcher() -> JobMatcher:
    global _matcher
    if _matcher is None:
        from job_engine.config import config

        _matcher = JobMatcher(str(config.profile_path))
    return _matcher


def get_scored_job(job_id: str) -> dict[str, Any] | None:
    """Load a single job by external_id and score it — O(1) DB lookup.

    Avoids scoring the entire table just to fetch one job (as an earlier
    get_scored_jobs()-then-linear-scan did).
    """
    engine = get_engine()
    with Session(engine) as session:
        job = (
            session.query(Job)
            .options(joinedload(Job.company_rel), joinedload(Job.applications))
            .filter(Job.external_id == job_id)
            .first()
        )
        if job is None:
            return None
        job_dict = job_to_dict(job)

    details = _get_matcher().score_detail(job_dict)
    return {
        **job_dict,
        "match_score": details["total_score"],
        "match_details": details,
    }


def load_companies_from_db(
    sort_by: str = "name",
    sort_order: str = "asc",
    q: str = "",
    job_id: str = "",
) -> list[dict]:
    """Load all companies with job counts from the database.

    Args:
        sort_by: Field to sort by — ``"name"`` or ``"job_count"``.
        sort_order: ``"asc"`` or ``"desc"``.
        q: Optional free-text search — matches company name, industry, headquarters.
        job_id: Optional job external_id — filters to only the company associated
                with that specific job.

    Uses a single GROUP BY query to fetch job counts, avoiding N+1 lazy loads.
    """
    # Sanitise sort params
    valid_sort_by = {"name", "job_count"}
    valid_sort_order = {"asc", "desc"}
    sort_by = sort_by if sort_by in valid_sort_by else "name"
    sort_order = sort_order if sort_order in valid_sort_order else "asc"
    reverse = sort_order == "desc"

    from sqlalchemy import func

    engine = get_engine()
    with Session(engine) as session:
        # Subquery: does any job at this company have an application?
        from job_engine.models import Application

        has_app_subq = (
            session.query(Application.id)
            .join(Job, Application.job_id == Job.id)
            .filter(Job.company_id == Company.id)
            .exists()
        )

        query = (
            session.query(
                Company,
                func.count(Job.id).label("job_count"),
                func.group_concat(func.distinct(Job.platform)).label("platforms"),
                has_app_subq.label("has_applications"),
            )
            .outerjoin(Job, Job.company_id == Company.id)
            .group_by(Company.id)
        )

        if job_id:
            query = query.filter(Job.external_id == job_id)

        if q:
            q_filter = q.lower()
            from sqlalchemy import or_

            query = query.having(
                or_(
                    func.lower(Company.name).contains(q_filter),
                    func.lower(Company.industry).contains(q_filter),
                    func.lower(Company.headquarters).contains(q_filter),
                )
            )

        rows = query.all()
        result = []
        for c, job_count, platforms_str, has_apps in rows:
            platforms = [p for p in (platforms_str or "").split(",") if p]
            result.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "url": c.url,
                    "logo_url": c.logo_url,
                    "industry": c.industry,
                    "size_range": c.size_range,
                    "headquarters": c.headquarters,
                    "founded_year": c.founded_year,
                    "description": c.description,
                    "linkedin_url": c.linkedin_url,
                    "job_count": job_count,
                    "platforms": platforms,
                    "has_applications": bool(has_apps),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
            )

        result.sort(
            key=lambda r: (
                (r.get(sort_by) or 0) if sort_by == "job_count" else (r.get(sort_by) or "")
            ),
            reverse=reverse,
        )
        return result


def load_profile() -> dict:
    """Load my_profile.yaml via ProfileConfig (single source of truth)."""
    return get_profile_config().load()

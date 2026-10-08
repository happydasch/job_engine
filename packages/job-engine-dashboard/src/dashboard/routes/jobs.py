from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import Job
from job_engine.task_manager import get_task_manager
from sqlalchemy.orm import Session

from dashboard.common import get_scored_job, get_scored_jobs, invalidate_scored_cache, job_to_dict
from dashboard.jobs_helpers import (
    collect_available_categories,
    collect_available_contract_types,
    collect_available_experience_levels,
    collect_available_locations,
    collect_available_platforms,
    collect_available_skills,
    filter_and_sort_jobs,
)
from dashboard.routes.route_helpers import get_job_or_404, toggle_job_field

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/jobs", response_class=JSONResponse)
async def api_jobs(
    request: Request,
    q: str = Query("", description="Free-text search"),
    sort_by: str = Query("match_score", description="Sort field"),
    sort_order: str = Query("desc", description="Sort direction (asc or desc)"),
    min_score: float = Query(0.0, description="Minimum match score filter"),
    platform: str = Query("", description="Platform filter"),
    remote: str = Query("", description="Remote filter"),
    show_hidden: str = Query("", description="Show hidden jobs"),
    hidden_only: str = Query("", description="Show only hidden jobs"),
    show_favorites: str = Query("", description="Show only favorites"),
    show_applied: str = Query("", description="Show only applied jobs"),
    show_enriched: str = Query("", description="Show only enriched (LLM-analyzed) jobs"),
    skill: str = Query("", description="Filter by skill/tech"),
    location: str = Query("", description="Filter by location (case-insensitive substring)"),
    experience_level: str = Query("", description="Filter by experience level"),
    category: str = Query("", description="Filter by category"),
    contract_type: str = Query("", description="Filter by contract type"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
):
    """JSON API: list scored, filtered, and paginated jobs."""

    all_jobs = get_scored_jobs()
    filtered = filter_and_sort_jobs(
        all_jobs,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
        min_score=min_score,
        platform=platform,
        remote=remote,
        show_hidden=show_hidden,
        hidden_only=hidden_only,
        show_favorites=show_favorites,
        show_applied=show_applied,
        show_enriched=show_enriched,
        skill=skill,
        location=location,
        experience_level=experience_level,
        category=category,
        contract_type=contract_type,
    )

    total = len(filtered)
    max_page = max(1, (total + per_page - 1) // per_page)
    page = min(page, max_page)
    start = (page - 1) * per_page
    page_jobs = filtered[start : start + per_page]

    # Collect filter metadata from unfiltered set
    platforms_available = collect_available_platforms(all_jobs)
    skills_available = collect_available_skills(all_jobs)
    locations_available = collect_available_locations(all_jobs)
    levels_available = collect_available_experience_levels(all_jobs)
    categories_available = collect_available_categories(all_jobs)
    contract_types_available = collect_available_contract_types(all_jobs)

    return {
        "jobs": page_jobs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "filters": {
            "platforms": platforms_available,
            "skills": skills_available,
            "locations": locations_available,
            "experience_levels": levels_available,
            "categories": categories_available,
            "contract_types": contract_types_available,
        },
    }


@router.get("/api/jobs/{job_id}", response_class=JSONResponse)
async def api_job_detail(job_id: str):
    """JSON API: single job detail with match breakdown."""
    job = get_scored_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _toggle_field_sync(job_id: str, field: str) -> dict:
    """Sync helper to toggle a boolean Job field with retry-on-lock."""
    from job_engine.database import _retry_on_lock

    @_retry_on_lock()
    def _do_toggle():
        engine = get_engine()
        with Session(engine) as session:
            job = get_job_or_404(session, job_id)
            new_val = toggle_job_field(session, job_id, field)
            result = {"external_id": job.external_id, field: new_val}
        # Drop the cached job list so the new value is visible to the list
        # filters (hidden_only / show_favorites / show_hidden) immediately.
        invalidate_scored_cache()
        return result

    return _do_toggle()


@router.patch("/api/jobs/{job_id}/toggle-hide", response_class=JSONResponse)
async def toggle_hide_job(job_id: str):
    """Toggle the hidden flag on a job."""
    return await asyncio.to_thread(_toggle_field_sync, job_id, "hidden")


@router.patch("/api/jobs/{job_id}/toggle-fav", response_class=JSONResponse)
async def toggle_fav_job(job_id: str):
    """Toggle the favorite flag on a job."""
    return await asyncio.to_thread(_toggle_field_sync, job_id, "favorite")


def _extract_text_from_html(content: str) -> str:
    """Strip a job page's HTML down to readable text (block structure preserved)."""
    # Remove script and style blocks (never contain job text)
    for tag in ("script", "style", "noscript", "svg"):
        content = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    # Add newlines after block-level closing tags to preserve structure
    for tag in (
        "/p",
        "/div",
        "/li",
        "/tr",
        "/section",
        "/article",
        "/blockquote",
        "/pre",
        "/h1",
        "/h2",
        "/h3",
        "/h4",
        "/h5",
        "/h6",
        "br[/>]",
        "/ul",
        "/ol",
        "/dl",
        "/table",
    ):
        content = re.sub(rf"(?i)<{tag}\s*>", "\n", content)
    # Convert <li> to bullet points
    content = re.sub(r"(?i)<li[^>]*>\s*", "  • ", content)
    # Strip remaining HTML tags
    content = re.sub(r"<[^>]+>", " ", content)
    # Decode common HTML entities
    for ent, ch in [
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&apos;", "'"),
    ]:
        content = content.replace(ent, ch)
    # Collapse horizontal whitespace but keep newlines
    content = re.sub(r"[ \t]+", " ", content)
    # Remove excessive blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    # Limit to 100k chars (plenty for any job posting)
    return content.strip()[:100000]


@router.post("/api/jobs/{job_id}/fetch-content", response_class=JSONResponse)
async def fetch_job_content(job_id: str):
    """Fetch the offer URL content, store it, and trigger background LLM analysis.

    The web fetch completes synchronously (fast, < 5s), then the LLM analysis
    runs in the background via the unified TaskManager.  The response includes
    a ``task_id`` that the frontend can poll for completion.

    A DB session is NEVER held open across the network fetch or the LLM calls.
    Doing so leaves an uncommitted write (fetched_content) on the connection for
    tens of seconds; a later autoflush then tries to upgrade a stale WAL
    snapshot to a write and deadlocks against the scraper's writes — surfacing
    as "database is locked". Instead: (1) read the URL in a short session,
    (2) fetch + clean off-session, (3) persist content immediately, (4) trigger
    a background LLM task.
    """
    from dashboard.routes.llm_task import _run_llm_analysis

    engine = get_engine()

    # ── 1) Load URL + base job_dict (short read-only session) ───────────────
    def _load() -> tuple[str, dict[str, Any]]:
        with Session(engine) as session:
            job = session.query(Job).filter(Job.external_id == job_id).first()
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            if not job.url:
                raise HTTPException(status_code=400, detail="Job has no URL")
            return job.url, job_to_dict(job)

    url, _job_dict = await asyncio.to_thread(_load)

    # ── 2) Fetch + clean (no DB session open) ───────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            resp.raise_for_status()
            content = _extract_text_from_html(resp.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {e}")

    # ── 3) Persist content immediately (short write, no LLM) ────────────────
    from job_engine.database import _retry_on_lock

    @_retry_on_lock()
    def _persist_content() -> None:
        with Session(engine) as session:
            job = session.query(Job).filter(Job.external_id == job_id).first()
            if job is None:
                return
            job.fetched_content = content
            job.updated_at = datetime.now(UTC)
            session.commit()

    await asyncio.to_thread(_persist_content)

    # ── 4) Trigger background LLM analysis via TaskManager ──────────────────
    # Read language from app settings for the analysis
    from job_engine.config import get_app_settings

    app_settings = get_app_settings().load()
    analysis_language = app_settings.get("language", "english")

    tm = get_task_manager()
    task_id = await tm.start(
        "llm_analysis",
        f"LLM Analysis: {job_id}",
        lambda t: _run_llm_analysis(t, job_id, language=analysis_language),
        metadata={"job_id": job_id, "language": analysis_language},
    )

    return {
        "external_id": job_id,
        "fetched": True,
        "length": len(content),
        "preview": content[:500],
        "task_id": task_id,
        "llm_triggered": True,
    }

"""
LLM task runner functions for the unified TaskManager.

These are async callables that receive a ``Task`` object and update it as
they progress.  They are registered with ``TaskManager.start()`` so that
LLM work is tracked the same way as scraper runs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from job_engine.database import get_sync_engine as get_engine
from job_engine.llm import (
    analyze_all_job,
    generate_application_letter,
    has_api_key,
    review_cover_letter,
)
from job_engine.models import Job
from job_engine.task_manager import Task
from sqlalchemy.orm import Session

from dashboard.common import job_to_dict, load_profile
from dashboard.jobs_helpers import _save_llm_fields_to_job

logger = logging.getLogger(__name__)

# Maps endpoint_type to (cache_field, response_key, parse_json)
LLM_ENDPOINTS: dict[str, tuple[str, str, bool]] = {
    "analyze": ("llm_analysis", "analysis", True),
    "explain": ("llm_explain_match", "explanation", True),
    "cover-letter": ("llm_cover_letter", "cover_letter", False),
    "questions": ("llm_questions", "questions", True),
}


async def _run_llm_analysis(task: Task, job_id: str, language: str | None = None) -> None:
    """Runner for combined LLM analysis.  Updates task as it progresses.

    Args:
        task: Task object for progress tracking.
        job_id: External ID of the job to analyze.
        language: Preferred output language. Falls back to profile's setting.
    """
    task.metadata["job_id"] = job_id
    task.metadata["language"] = language
    task.progress_pct = 5.0
    task.add_log("Loading job from database…")

    engine = get_engine()

    def _load_job() -> dict[str, Any] | None:
        with Session(engine) as session:
            job = session.query(Job).filter(Job.external_id == job_id).first()
            if job is None:
                return None
            return job_to_dict(job)

    job_dict = await asyncio.to_thread(_load_job)
    if job_dict is None:
        task.status = "failed"
        task.error_message = f"Job {job_id} not found"
        task.add_log(f"ERROR: Job {job_id} not found")
        return

    if not has_api_key():
        task.status = "failed"
        task.error_message = "No LLM API key configured"
        task.add_log("ERROR: No LLM API key configured")
        return

    task.progress_pct = 20.0
    task.add_log("Loading profile…")
    profile = load_profile()

    resolved_language = language or profile.get("language", "english")

    task.progress_pct = 30.0
    task.add_log("Running combined LLM analysis…")

    combined = await asyncio.to_thread(
        analyze_all_job, job_dict, profile, language=resolved_language
    )

    if combined:
        task.progress_pct = 80.0
        task.add_log("Saving LLM results to database…")
        await asyncio.to_thread(_save_llm_fields_to_job, job_id, combined)
        task.progress_pct = 100.0
        task.result = {
            "cached": False,
            "analysis": combined.get("analysis"),
            "explanation": combined.get("explain_match"),
            "cover_letter": combined.get("cover_letter"),
            "questions": combined.get("questions"),
            "summary": combined.get("summary"),
        }
        task.status = "completed"
        task.add_log("LLM analysis complete")
    else:
        task.status = "failed"
        task.error_message = "LLM returned no result"
        task.add_log("ERROR: LLM returned no result")


async def _run_llm_application_letter(
    task: Task,
    job_id: str,
    language: str | None = None,
    style: str = "professional",
    tone: str = "neutral",
    length: str = "medium",
    draft: str | None = None,
    review: bool = False,
) -> None:
    """Runner for application letter generation, with an optional reviewer pass."""
    task.metadata["job_id"] = job_id
    task.metadata["settings"] = {
        "language": language,
        "style": style,
        "tone": tone,
        "length": length,
        "has_draft": draft is not None,
        "review": review,
    }
    task.progress_pct = 5.0
    task.add_log("Loading job from database…")

    engine = get_engine()

    def _load_job() -> dict[str, Any] | None:
        with Session(engine) as session:
            job = session.query(Job).filter(Job.external_id == job_id).first()
            if job is None:
                return None
            return job_to_dict(job)

    job_dict = await asyncio.to_thread(_load_job)
    if job_dict is None:
        task.status = "failed"
        task.error_message = f"Job {job_id} not found"
        return

    if not has_api_key():
        task.status = "failed"
        task.error_message = "No LLM API key configured"
        return

    task.progress_pct = 20.0
    task.add_log("Loading profile…")
    profile = load_profile()

    resolved_language = language or profile.get("language", "english")

    task.progress_pct = 40.0
    task.add_log(f"Generating {style} application letter in {resolved_language}…")

    letter = await asyncio.to_thread(
        generate_application_letter,
        job_dict,
        profile,
        language=resolved_language,
        style=style,
        tone=tone,
        length=length,
        draft=draft,
    )

    reviewed = False
    if letter and review:
        task.progress_pct = 70.0
        task.add_log("Reviewing draft (second pass)…")
        review_result = await asyncio.to_thread(
            review_cover_letter, letter, job_dict, profile, resolved_language
        )
        reviewed = review_result["reviewed"]
        letter = review_result["revised_text"]
        if not reviewed:
            task.add_log("WARNING: review pass failed, returning unreviewed draft")

    if letter:
        task.progress_pct = 100.0
        task.result = {
            "letter": letter,
            "reviewed": reviewed,
            "language": resolved_language,
            "style": style,
            "tone": tone,
            "length": length,
        }
        task.status = "completed"
        task.add_log("Application letter generated")
    else:
        task.status = "failed"
        task.error_message = "LLM returned no letter"
        task.add_log("ERROR: LLM returned no letter")

"""Skills / skill gap analysis route for the dashboard."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from job_engine.skill_gap import analyze_skill_gaps, format_gap_summary

from dashboard.common import get_scored_jobs, load_profile

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/skills")
async def api_skills():
    """Return skill gap analysis as JSON."""
    jobs = get_scored_jobs()
    profile = load_profile()

    report = analyze_skill_gaps(jobs, profile)
    summary = format_gap_summary(report)

    return JSONResponse(summary)

"""
LLM routes — read-only cache lookup only.

All long-running LLM work (analysis, application letters, etc.) is triggered
via ``POST /api/tasks/llm`` in the ``tasks`` router and runs in the background
through the unified ``TaskManager``.  The frontend polls ``GET /api/tasks/{id}``
for completion and then reads cached results via ``GET /api/jobs/{id}/analysis``.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import Job
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter()


# ── GET cached analysis (read-only, all fields) ───────────────────────────────


@router.get("/api/jobs/{job_id}/analysis", response_class=JSONResponse)
async def api_get_analysis(job_id: str):
    """Return cached LLM analysis for a job — includes analysis, explain match,
    cover letter, and interview questions if they were pre-generated."""
    engine = get_engine()
    with Session(engine) as session:
        job = session.query(Job).filter(Job.external_id == job_id).first()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        result = {"status": "not_analyzed"}

        if job.llm_analysis:
            try:
                result["analysis"] = json.loads(job.llm_analysis)
                result["status"] = "ok"
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupt llm_analysis JSON for job %s — ignoring", job_id)

        if job.llm_explain_match:
            try:
                result["explain_match"] = json.loads(job.llm_explain_match)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupt llm_explain_match JSON for job %s — ignoring", job_id)

        if job.llm_cover_letter:
            result["cover_letter"] = job.llm_cover_letter

        if job.llm_questions:
            try:
                result["questions"] = json.loads(job.llm_questions)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Corrupt llm_questions JSON for job %s — ignoring", job_id)

        return JSONResponse(result)

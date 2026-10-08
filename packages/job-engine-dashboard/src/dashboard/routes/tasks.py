"""
Generic task CRUD endpoints for the unified TaskManager.

All long-running background work (scrapers, LLM analysis, etc.) is tracked
through the same ``TaskManager`` and can be polled via these endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from job_engine.task_manager import get_task_manager

from dashboard.routes.llm_task import _run_llm_analysis, _run_llm_application_letter

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Task CRUD ────────────────────────────────────────────────────────────────


@router.get("/api/tasks", response_class=JSONResponse)
async def api_list_tasks(
    task_type: str | None = Query(None, description="Filter by task type"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """List tasks, optionally filtered by type/status."""
    tm = get_task_manager()
    tasks = tm.list(task_type=task_type, status=status, limit=limit)
    return JSONResponse({"tasks": [t.to_dict() for t in tasks], "total": len(tasks)})


@router.get("/api/tasks/{task_id}", response_class=JSONResponse)
async def api_get_task(task_id: str):
    """Get the full state of a single task (status, result, error, progress)."""
    tm = get_task_manager()
    task = tm.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return JSONResponse(task.to_dict())


@router.delete("/api/tasks/{task_id}", response_class=JSONResponse)
async def api_cancel_task(task_id: str):
    """Cancel a running task."""
    tm = get_task_manager()
    try:
        result = tm.cancel(task_id)
        return JSONResponse({"success": True, "task": result})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


@router.get("/api/tasks/{task_id}/logs", response_class=JSONResponse)
async def api_get_task_logs(
    task_id: str,
    offset: int = Query(0, ge=0, description="Log line offset for tailing"),
):
    """Return log lines for a task (offset-based pagination)."""
    tm = get_task_manager()
    try:
        return JSONResponse(tm.get_logs(task_id, offset=offset))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found") from None


# ── LLM task triggers ─────────────────────────────────────────────────────────


@router.post("/api/tasks/llm", response_class=JSONResponse)
async def api_trigger_llm_task(body: dict):
    """Start an LLM analysis task in the background.

    JSON body:
      - ``job_id`` (required): the job's external_id
      - ``task_type`` (optional): ``"llm_analysis"`` (default) or ``"llm_application_letter"``
      - For ``llm_application_letter``:
        - ``language``, ``style``, ``tone``, ``length``, ``draft`` — application letter settings
        - ``review`` (bool) — run a second reviewer pass over the generated letter

    Returns ``{"task_id": "..."}`` immediately.
    """
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="'job_id' is required")

    task_type = body.get("task_type", "llm_analysis")
    tm = get_task_manager()

    if task_type == "llm_analysis":
        task_id = await tm.start(
            "llm_analysis",
            f"LLM Analysis: {job_id}",
            lambda t: _run_llm_analysis(t, job_id, language=body.get("language")),
            metadata={
                "job_id": job_id,
                "language": body.get("language"),
            },
        )
    elif task_type == "llm_application_letter":
        task_id = await tm.start(
            "llm_application_letter",
            f"Application Letter: {job_id}",
            lambda t: _run_llm_application_letter(
                t,
                job_id,
                language=body.get("language"),
                style=body.get("style", "professional"),
                tone=body.get("tone", "neutral"),
                length=body.get("length", "medium"),
                draft=body.get("draft"),
                review=bool(body.get("review", False)),
            ),
            metadata={"job_id": job_id},
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task_type: {task_type}")

    return JSONResponse({"task_id": task_id, "status": "running"})

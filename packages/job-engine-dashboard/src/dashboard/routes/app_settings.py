"""App settings API routes — manage app_settings.yaml from the dashboard."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from job_engine.config import get_app_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/app-settings")
async def get_settings():
    """Return the full app settings as JSON."""
    settings = get_app_settings().load()
    return JSONResponse(content=settings)


@router.patch("/api/app-settings")
async def update_settings(request: Request):
    """Update a section of the app settings.

    Expects JSON body: ``{"section": "...", "values": ...}``

    Returns the updated full settings on success.
    """
    body = await request.json()
    section = body.get("section")
    values = body.get("values")

    if not section:
        raise HTTPException(status_code=400, detail="Missing 'section' field")
    if values is None:
        raise HTTPException(status_code=400, detail="Missing 'values' field")

    cfg = get_app_settings()
    try:
        updated = cfg.update_section(section, values)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")

    return JSONResponse(
        content={
            "status": "ok",
            "section": section,
            "settings": updated,
        }
    )

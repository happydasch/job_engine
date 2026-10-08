"""Health check endpoint for the Job Engine Dashboard.

Returns JSON with system status, version, and lightweight checks.
Used by monitoring tools and the dashboard UI to verify the app is healthy.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from fastapi import APIRouter
from job_engine import __version__

logger = logging.getLogger(__name__)

router = APIRouter()

# Track server start time for uptime calculation
_server_start = time.time()

# ── Version ────────────────────────────────────────────────────────────────────


_VERSION = __version__


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/api/health")
async def health_check():
    """Return system health status as JSON.

    Responses:
        - status: "ok" | "degraded" | "error"
        - version: project version from VERSION file
        - checks: dict of individual check results
        - uptime_seconds: seconds since server started
    """
    checks: dict[str, dict] = {}

    # — DB connectivity —
    try:
        from job_engine.database import get_sync_engine
        from sqlalchemy import text

        engine = get_sync_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
        ok = row is not None and row[0] == 1
        checks["database"] = {
            "status": "ok" if ok else "error",
            "detail": "query returned 1" if ok else "SELECT 1 returned unexpected result",
        }
        engine.dispose()
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}

    # — Disk space —
    try:
        data_dir = Path(__file__).resolve().parent.parent.parent.parent.parent.parent / "data"
        usage = shutil.disk_usage(data_dir)
        free_gb = usage.free / (1024**3)
        if free_gb < 0.1:
            disk_status = "error"
        elif free_gb < 0.5:
            disk_status = "degraded"
        else:
            disk_status = "ok"
        checks["disk"] = {
            "status": disk_status,
            "free_gb": round(free_gb, 1),
            "total_gb": round(usage.total / (1024**3), 1),
        }
    except Exception as exc:
        checks["disk"] = {"status": "error", "detail": str(exc)}

    # — Profile exists —
    profile_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent.parent
        / "data"
        / "my_profile.yaml"
    )
    checks["profile"] = {
        "status": "ok" if profile_path.exists() else "degraded",
        "detail": "found" if profile_path.exists() else "not found (scoring will fail)",
    }

    # — Overall status —
    statuses = [c["status"] for c in checks.values()]
    if "error" in statuses:
        overall = "error"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "ok"

    uptime = round(time.time() - _server_start, 1)

    return {
        "status": overall,
        "version": _VERSION,
        "uptime_seconds": uptime,
        "checks": checks,
    }


@router.get("/api/version")
async def get_version():
    """Return the project version from the VERSION file.

    Responses:
        - version: project version string
        - build_date: build/release date
    """
    return {
        "version": _VERSION,
        "build_date": "2026-07-24",
    }

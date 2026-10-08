"""Scraper management and scraper catalog routes
— runs, schedule, catalog, catalog browse/install."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import ScraperLog
from job_engine.scraper_catalog_config import (
    add_catalog,
    list_catalogs,
    remove_catalog,
    update_catalog,
)
from job_engine.scraper_config import (
    get_catalog_scrapers,
    get_scraper_config,
    install_scraper,
    refresh_catalog_cache,
    refresh_scraper_metadata,
    reinstall_all_scrapers,
    reinstall_scraper,
    uninstall_scraper,
)
from job_engine.scraper_runner import ScraperRun, get_scraper_manager
from job_engine.task_manager import get_task_manager
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ── HTML Pages ─────────────────────────────────────────────────────────────


@router.get("/api/scrape/scrapers", response_class=JSONResponse)
async def api_scrape_scrapers():
    """List all scrapers with their enabled/disabled state."""
    cfg = get_scraper_config()
    return JSONResponse({"scrapers": cfg.list_scrapers()})


class ScraperEnabledUpdate(BaseModel):
    enabled: bool


@router.put("/api/scrape/scrapers/{scraper_id}", response_class=JSONResponse)
async def api_scrape_toggle_scraper(scraper_id: str, body: ScraperEnabledUpdate):
    """Set a scraper's enabled state to the requested value."""
    cfg = get_scraper_config()
    if scraper_id not in {p["id"] for p in cfg.list_scrapers()}:
        raise HTTPException(status_code=404, detail=f"Unknown scraper: {scraper_id}")
    new_state = cfg.set_scraper(scraper_id, body.enabled)
    return JSONResponse({"scraper_id": scraper_id, "enabled": new_state})


@router.get("/api/scrape/scrapers/{scraper_id}/config", response_class=JSONResponse)
async def api_scraper_get_config(scraper_id: str):
    """Return the config schema + current values for a scraper."""
    cfg = get_scraper_config()
    fields_schema = cfg.get_scraper_config_fields(scraper_id)
    current_config = cfg.get_scraper_full_config(scraper_id)
    return JSONResponse(
        {
            "scraper_id": scraper_id,
            "fields": fields_schema or {},
            "values": current_config or {},
        }
    )


@router.put("/api/scrape/scrapers/{scraper_id}/config", response_class=JSONResponse)
async def api_scraper_update_config(scraper_id: str, request: Request):
    """Update one or more config fields for a scraper."""
    body = await request.json()
    cfg = get_scraper_config()
    for field, value in body.items():
        cfg.set_scraper_field(scraper_id, field, value)
    return JSONResponse({"success": True, "scraper_id": scraper_id})


@router.get("/api/scrape/schedule", response_class=JSONResponse)
async def api_scrape_schedule_get():
    """Get the current scheduler configuration."""
    manager = get_scraper_manager()
    return JSONResponse(manager.get_scheduler_config())


@router.put("/api/scrape/schedule", response_class=JSONResponse)
async def api_scrape_schedule_set(request: Request):
    """Update scheduler configuration (enabled, interval_minutes)."""
    body = await request.json()
    manager = get_scraper_manager()
    result = await manager.set_scheduler_config(
        enabled=body.get("enabled"),
        interval_minutes=body.get("interval_minutes"),
    )
    return JSONResponse(result)


# ── Scrape start (consolidated) ──────────────────────────────────────────────


@router.post("/api/scrape", response_class=JSONResponse)
async def api_scrape_start(scraper_id: str | None = None):
    """Start a scraper run. If scraper_id provided, run single scraper only.

    Returns the unified task_id.  Poll ``GET /api/tasks/{task_id}`` for status.
    """
    manager = get_scraper_manager()
    try:
        kwargs = {"scraper_ids": [scraper_id]} if scraper_id else {}
        task_id = await manager.start_run(**kwargs)
        task = get_task_manager().get(task_id)
        resp: dict[str, object] = {
            "task_id": task_id,
            "status": "running",
            "started_at": task.started_at.isoformat() if task else None,
        }
        if scraper_id:
            resp["scraper_id"] = scraper_id
        return JSONResponse(resp)
    except RuntimeError as e:
        active = get_task_manager().get_active("scraper_run")
        return JSONResponse(
            {
                "error": str(e),
                "task_id": active.task_id if active else None,
                "status": "running" if active else "idle",
            },
            status_code=409,
        )


@router.post("/api/scrape/scraper/{scraper_id}", response_class=JSONResponse)
async def api_scrape_start_scraper(scraper_id: str):
    """Start a scraper run for a single scraper only (legacy wrapper)."""
    return await api_scrape_start(scraper_id=scraper_id)


def _get_ever_run_scrapers() -> list[str]:
    """Query the ScraperLog table for distinct scraper IDs that have ever been run."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    engine = get_engine()
    with Session(engine) as session:
        rows = (
            session.execute(
                select(ScraperLog.scraper)
                .distinct()
                .where(~ScraperLog.scraper.startswith("dashboard_run_"))
            )
            .scalars()
            .all()
        )
    return list(rows)


@router.get("/api/scrape/status", response_class=JSONResponse)
async def api_scrape_status():
    """Get the status of the current or last scraper run via TaskManager."""

    tm = get_task_manager()
    task = tm.get_active("scraper_run")
    if task is not None:
        run: ScraperRun | None = task.metadata.get("scraper_run")
        if run:
            resp = run.to_dict()
            resp["ever_run_scrapers"] = _get_ever_run_scrapers()
            return JSONResponse(resp)

    # Fall back to last completed run
    tasks = tm.list(task_type="scraper_run", limit=1)
    if tasks:
        task = tasks[0]
        run = task.metadata.get("scraper_run")
        if run:
            resp = run.to_dict()
            resp["ever_run_scrapers"] = _get_ever_run_scrapers()
            return JSONResponse(resp)

    return JSONResponse({"status": "idle", "last_run": None, "ever_run_scrapers": []})


@router.get("/api/scrape/status/{task_id}", response_class=JSONResponse)
async def api_scrape_status_by_id(task_id: str):
    """Get the status of a specific scraper run by task_id."""
    tm = get_task_manager()
    task = tm.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    run: ScraperRun | None = task.metadata.get("scraper_run")
    if run is None:
        raise HTTPException(status_code=404, detail="No scraper state for this task")
    return JSONResponse(run.to_dict())


@router.get("/api/scrape/history", response_class=JSONResponse)
async def api_scrape_history(limit: int = Query(20, description="Number of history entries")):
    """Get historical scraper run logs."""
    manager = get_scraper_manager()
    return JSONResponse(manager.get_run_history(limit=limit))


@router.get("/api/scrape/logs/{task_id}", response_class=JSONResponse)
async def api_scrape_logs(
    task_id: str,
    offset: int = Query(0, ge=0, description="Return log lines from this index (live tail)"),
):
    """Get collected log lines + issues from a scraper run via TaskManager.

    Live runs stream from memory (poll with next_offset); finished runs are
    read back from the persisted log file and the run's DB record.
    """
    manager = get_scraper_manager()
    try:
        return JSONResponse(manager.get_run_logs(task_id, offset=offset))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No logs found for task {task_id}") from None


@router.post("/api/scrape/cancel/{task_id}", response_class=JSONResponse)
async def api_scrape_cancel(task_id: str):
    """Cancel a running scraper run by task_id."""
    manager = get_scraper_manager()
    try:
        result = await manager.cancel_run(task_id)
        return JSONResponse({"success": True, "run": result})
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)


# ── JSON API — Scraper Catalog ────────────────────────────────────────


@router.get("/api/scrapers/catalog/list")
async def api_catalog_list(request: Request, refresh: bool = False):
    """Return all scrapers from the catalog with installed status.

    Pass ?refresh=true to force re-read the catalog file and registry metadata.
    """
    if refresh:
        refresh_catalog_cache()
        refresh_scraper_metadata()

    scrapers = get_catalog_scrapers()

    return JSONResponse(content={"scrapers": scrapers, "total": len(scrapers)})


@router.get("/api/scrapers/catalog/search")
async def api_catalog_search(request: Request, q: str = ""):
    """Search scrapers by name, description, or category.

    Returns matching scrapers with installed status.
    """
    scrapers = get_catalog_scrapers()

    if q:
        q_lower = q.lower()
        scrapers = [
            p
            for p in scrapers
            if q_lower in p["id"].lower()
            or q_lower in p["name"].lower()
            or q_lower in p["description"].lower()
            or q_lower in p["category"].lower()
        ]

    return JSONResponse(content={"scrapers": scrapers, "total": len(scrapers), "query": q})


# ── JSON API — Scraper Catalog Install/Uninstall (consolidated) ──────────────────


@router.post("/api/scrapers/catalog/reinstall/{scraper_id}")
async def api_catalog_reinstall(scraper_id: str):
    """Reinstall a single scraper (uninstall + install).

    Calls ``reinstall_scraper()`` which uninstalls then reinstalls
    the scraper, returning the result.
    """
    result = reinstall_scraper(scraper_id)
    if result["success"]:
        return JSONResponse(
            content={
                "success": True,
                "message": f"Reinstalled {scraper_id}",
                "version": result.get("version", ""),
            },
            status_code=200,
        )
    else:
        return JSONResponse(
            content={"success": False, "error": result.get("error", "Reinstall failed")},
            status_code=400,
        )


@router.post("/api/scrapers/catalog/{action}/{scraper_id}")
async def api_catalog_action(action: str, scraper_id: str):
    """Install or uninstall a scraper package.

    Calls the Node.js install-scraper CLI and returns the result.
    """
    if action not in ("install", "uninstall"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{action}'. Allowed: install, uninstall",
        )

    result = install_scraper(scraper_id) if action == "install" else uninstall_scraper(scraper_id)
    if result["success"]:
        return JSONResponse(
            content={
                "success": True,
                "message": f"{action.capitalize()}ed {scraper_id}",
                "output": result.get("output", ""),
            },
            status_code=200,
        )
    else:
        return JSONResponse(
            content={"success": False, "error": result.get("error", "Unknown error")},
            status_code=400,
        )


@router.post("/api/scrapers/catalog/install/{scraper_id}")
async def api_catalog_install(scraper_id: str):
    """Install a scraper (legacy wrapper)."""
    return await api_catalog_action("install", scraper_id)


@router.post("/api/scrapers/catalog/uninstall/{scraper_id}")
async def api_catalog_uninstall(scraper_id: str):
    """Uninstall a scraper (legacy wrapper)."""
    return await api_catalog_action("uninstall", scraper_id)


@router.post("/api/scrapers/catalog/reinstall-all")
async def api_catalog_reinstall_all():
    """Reinstall all currently installed scrapers.

    Sequentially uninstalls and reinstalls each installed scraper.
    Returns a summary with per-scraper results.
    """
    result = reinstall_all_scrapers()
    if result["success"]:
        return JSONResponse(content=result, status_code=200)
    else:
        return JSONResponse(content=result, status_code=400)


# ── JSON API — Catalog Management ────────────────────────────────────────────


@router.get("/api/scrapers/catalog/catalogs")
async def api_catalog_list_catalogs(request: Request):
    """List all configured catalogs."""
    catalogs = list_catalogs()
    result = []
    for c in catalogs:
        d = c.to_dict()
        result.append(d)
    return JSONResponse(content={"catalogs": result, "total": len(result)})


@router.post("/api/scrapers/catalog/catalogs")
async def api_catalog_add_catalog(request: Request):
    """Add a new catalog."""
    body = await request.json()
    result = add_catalog(body)
    if result["success"]:
        return JSONResponse(content={"success": True, "message": "Catalog added"}, status_code=201)
    else:
        return JSONResponse(
            content={"success": False, "error": result.get("error", "Unknown error")},
            status_code=400,
        )


@router.put("/api/scrapers/catalog/catalogs/{catalog_id}")
async def api_catalog_update_catalog(catalog_id: str, request: Request):
    """Update a catalog's configuration."""
    body = await request.json()
    result = update_catalog(catalog_id, body)
    if result["success"]:
        return JSONResponse(content={"success": True, "message": f"Catalog {catalog_id} updated"})
    else:
        return JSONResponse(
            content={"success": False, "error": result.get("error", "Unknown error")},
            status_code=400,
        )


@router.delete("/api/scrapers/catalog/catalogs/{catalog_id}")
async def api_catalog_remove_catalog(catalog_id: str):
    """Remove a catalog."""
    result = remove_catalog(catalog_id)
    if result["success"]:
        return JSONResponse(content={"success": True, "message": f"Catalog {catalog_id} removed"})
    else:
        return JSONResponse(
            content={"success": False, "error": result.get("error", "Unknown error")},
            status_code=400,
        )


# ── JSON API — Scraper Source Code Viewer ────────────────────────────────


@router.get("/api/scrapers/catalog/source/{scraper_id}")
async def api_catalog_source(scraper_id: str):
    """Return the scraper's source files (index.js, package.json, README.md).

    Reads from the source directory at packages/job-engine-scrapers/scrapers/<id>/.
    Falls back to the active wrapper at data/active-scrapers/<id>/ if source
    is not found.
    """
    # Resolve the scraper source directory
    candidates = [
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "..",
                "..",
                "..",
                "packages/job-engine-scrapers/scrapers",
                scraper_id,
            )
        ),
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "..",
                "..",
                "..",
                "data/active-scrapers",
                scraper_id,
            )
        ),
    ]

    source_dir = None
    for d in candidates:
        if os.path.isdir(d):
            source_dir = d
            break

    if not source_dir:
        raise HTTPException(
            status_code=404,
            detail=f"Scraper '{scraper_id}' not found on disk. Tried: {', '.join(candidates)}",
        )

    # Read the files
    files = {}
    for name in ("index.js", "package.json", "README.md"):
        path = os.path.join(source_dir, name)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    files[name] = fh.read()
            except Exception as exc:
                files[name] = f"# Error reading {name}: {exc}"

    return JSONResponse(
        content={
            "scraper_id": scraper_id,
            "source_dir": source_dir,
            "files": files,
            "file_count": len(files),
        }
    )

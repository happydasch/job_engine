from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import ScraperLog
from job_engine.scraper_runner import get_scraper_manager
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from dashboard.common import get_scored_jobs
from dashboard.routes.route_helpers import compute_dashboard_stats

router = APIRouter()


@router.get("/api/dashboard/stats")
async def api_dashboard_stats():
    """JSON API: dashboard summary statistics."""
    jobs = get_scored_jobs()
    visible_jobs = [j for j in jobs if not j.get("hidden", False)]
    stats = compute_dashboard_stats(visible_jobs)

    manager = get_scraper_manager()
    scheduler = manager.get_scheduler_config()

    # Last 5 scraper runs from the ScraperLog table
    engine = get_engine()
    with Session(engine) as session:
        rows = (
            session.execute(
                select(ScraperLog)
                .where(ScraperLog.scraper.startswith("dashboard_run_"))
                .order_by(desc(ScraperLog.run_at))
                .limit(5)
            )
            .scalars()
            .all()
        )

    jobs_per_run = []
    for row in rows:
        started_at = row.run_at.isoformat()
        if row.run_at.tzinfo is None:
            started_at += "+00:00"
        details = json.loads(row.details) if row.details else {}
        jobs_per_run.append(
            {
                "run_id": details.get("run_id", row.scraper),
                "started_at": started_at,
                "status": row.status,
                "jobs_found": row.jobs_found,
                "jobs_new": details.get("jobs_new_seeded", 0),
                "scrapers": list(details.get("scraper_statuses", {}).keys()),
                "scraper_job_counts": details.get("scraper_job_counts", {}),
                "duration": row.duration_seconds,
            }
        )

    # ── Scraper health: per-scraper success/failure stats ────────────────
    from sqlalchemy import func

    scraper_health = {}
    with Session(engine) as session:
        subq = (
            select(
                ScraperLog.scraper,
                ScraperLog.status,
                func.count().label("cnt"),
            )
            .where(~ScraperLog.scraper.startswith("dashboard_run_"))
            .group_by(ScraperLog.scraper, ScraperLog.status)
            .subquery()
        )
        rows = session.execute(select(subq)).all()

    scraper_totals: dict[str, dict[str, int]] = {}
    for row in rows:
        name = row.scraper
        if name not in scraper_totals:
            scraper_totals[name] = {"success": 0, "partial": 0, "failed": 0, "total": 0}
        scraper_totals[name][row.status] = row.cnt
        scraper_totals[name]["total"] += row.cnt

    for name, counts in scraper_totals.items():
        total = counts["total"]
        scraper_health[name] = {
            "success_rate": round(counts["success"] / max(total, 1) * 100),
            "total_runs": total,
            "last_status": "success" if counts["failed"] == 0 else "partial",
        }

    return JSONResponse(
        {
            **stats,
            "scheduler": scheduler,
            "jobs_per_run": jobs_per_run,
            "scraper_health": scraper_health,
        }
    )


@router.get("/api/setup/status")
async def api_setup_status():
    """JSON API: first-run setup status — what's configured and what's missing."""
    from pathlib import Path

    from job_engine.config import config
    from job_engine.database import get_sync_engine as get_engine
    from job_engine.models import Job
    from job_engine.scraper_catalog_config import list_catalogs
    from sqlalchemy import func
    from sqlalchemy.orm import Session

    profile_path: Path = config.profile_path
    profile_exists = profile_path.exists()

    # Catalog sources
    try:
        catalogs = list_catalogs()
        catalogs_configured = len(catalogs)
    except Exception:
        catalogs_configured = 0

    # Installed scrapers (active-scrapers/<id>/package.json)
    active_scrapers_dir = config.project_root / "data" / "active-scrapers"
    scrapers_installed = 0
    if active_scrapers_dir.exists():
        scrapers_installed = len([d for d in active_scrapers_dir.iterdir() if d.is_dir()])

    # Available scrapers in the catalog source directories
    scrapers_available = 0
    try:
        from job_engine.scraper_config import get_catalog_scrapers

        scrapers_available = len(get_catalog_scrapers())
    except Exception:
        pass

    # Jobs in database
    jobs_in_database = 0
    try:
        engine = get_engine()
        with Session(engine) as session:
            jobs_in_database = session.execute(select(func.count(Job.id))).scalar() or 0
    except Exception:
        pass

    # Database initialized (always true if the app started without error)
    database_initialized = True

    steps = [
        {
            "id": "profile",
            "label": "Create your profile",
            "done": profile_exists,
            "action": "sidebar:profile",
        },
        {
            "id": "install",
            "label": "Install scrapers",
            "done": scrapers_installed > 0,
            "action": "/scrapers?tab=catalog",
        },
        {
            "id": "scrape",
            "label": "Run scrapers",
            "done": jobs_in_database > 0,
            "action": "/scrapers",
        },
    ]

    return JSONResponse(
        {
            "profile_exists": profile_exists,
            "scrapers_installed": scrapers_installed,
            "scrapers_available": scrapers_available,
            "catalogs_configured": catalogs_configured,
            "jobs_in_database": jobs_in_database,
            "database_initialized": database_initialized,
            "steps": steps,
        }
    )

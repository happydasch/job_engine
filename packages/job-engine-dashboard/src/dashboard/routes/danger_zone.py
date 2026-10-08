"""Danger Zone API routes — destructive actions (DB reset, scraper cleanup)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from job_engine.config import config, get_app_settings
from job_engine.database import get_sync_engine
from job_engine.models import Base

logger = logging.getLogger(__name__)

router = APIRouter()


def _scraper_output_path() -> Path:
    """Return the scraper output directory from config."""
    return config.scraper_output_dir


@router.post("/api/danger-zone/reset-database")
async def reset_database():
    """Drop all application tables and recreate them.

    Destructive: loses all jobs, companies, applications, skills, scraper logs.
    App settings, profile, and scraper configs are preserved.
    Onboarding dismissed flag is reset so the checklist shows again.
    """
    engine = get_sync_engine()

    try:
        # Get all ORM-registered table names
        table_names = list(Base.metadata.tables.keys())
        logger.info("Dropping tables: %s", table_names)

        # Drop all tables and recreate
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

        # Also run migration logic in case new columns are expected
        from job_engine.database import migrate_existing_db

        migrate_existing_db(engine)

        # Reset onboarding dismissed state so the checklist shows again
        try:
            settings = get_app_settings()
            settings.update_section("onboarding", {"dismissed": False})
            logger.info("Onboarding dismissed state reset")
        except Exception:
            logger.warning("Failed to reset onboarding dismissed state", exc_info=True)

        logger.info("Database reset complete — tables recreated")
        return JSONResponse(
            content={"status": "ok", "detail": f"Dropped and recreated {len(table_names)} tables"}
        )
    except Exception as exc:
        logger.exception("Database reset failed")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": f"Database reset failed: {exc}"},
        )


@router.post("/api/danger-zone/reset-scraper")
async def reset_scraper():
    """Remove all scraper output JSON files and log files.

    Destructive: loses scraped job data that hasn't been imported yet.
    Does NOT touch the database — only the scraper-output/ directory.
    """
    output_dir = _scraper_output_path()

    if not output_dir.exists():
        return JSONResponse(
            content={
                "status": "ok",
                "detail": "Scraper output directory does not exist — nothing to clean",
            }
        )

    try:
        removed_files = 0

        # Remove all .json files in the root of scraper-output
        for f in output_dir.glob("*.json"):
            f.unlink()
            removed_files += 1

        # Remove log files
        logs_dir = output_dir / "logs"
        if logs_dir.exists():
            shutil.rmtree(logs_dir)
            removed_files += 1

        # Remove raw subdirectory
        raw_dir = output_dir / "raw"
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
            removed_files += 1

        # Remove runs subdirectory (run history)
        runs_dir = output_dir / "runs"
        if runs_dir.exists():
            shutil.rmtree(runs_dir)
            removed_files += 1

        # Also remove any .yaml dashboard config remnants
        for f in output_dir.glob("_dashboard_config_*.yaml"):
            f.unlink()
            removed_files += 1

        logger.info("Scraper reset complete — removed %d files/directories", removed_files)
        return JSONResponse(
            content={
                "status": "ok",
                "detail": f"Cleaned scraper output — removed {removed_files} items",
            }
        )
    except Exception as exc:
        logger.exception("Scraper reset failed")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": f"Scraper reset failed: {exc}"},
        )

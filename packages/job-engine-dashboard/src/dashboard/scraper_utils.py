"""Scraper status utility — shared helper for building the scraper_status dict.

Both the overview dashboard and the scrapers page need to produce the same
scraper_status dictionary from the ScraperRunManager. This module extracts
that logic into a single call site.
"""

from __future__ import annotations

from job_engine.scraper_runner import get_scraper_manager


def get_scraper_status_dict() -> dict:
    """Build a scraper_status dict suitable for template rendering.

    Returns the active run if one is running, otherwise the last completed
    run, or a default ``{status: "idle", …}`` dict if there is no run history.

    The overview route historically overrides the last-run's status to
    ``"idle"`` while the scrapers page preserves the real status — this
    helper returns the raw status from the manager; callers may override
    as needed.
    """
    manager = get_scraper_manager()
    active_run = manager.get_active_run()
    last_run = manager.get_last_run()
    if active_run:
        return active_run.to_dict()
    if last_run:
        return last_run.to_dict()
    return {
        "status": "idle",
        "scrapers_total": 0,
        "scrapers_completed": 0,
        "scraper_statuses": {},
    }

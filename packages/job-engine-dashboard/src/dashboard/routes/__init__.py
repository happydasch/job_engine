"""Route modules for the Job Engine Dashboard.

Aggregates all route sub-modules so api/main.py can include them cleanly.
Provides ``router_registry`` — a list of all APIRouter instances.
"""

from __future__ import annotations

from dashboard.routes import (
    app_settings,
    applications,
    companies,
    danger_zone,
    health,
    jobs,
    llm,
    overview,
    plugins,
    profile,
    scrapers,
    skills,
    tasks,
    templates,
)

router_registry = [
    overview.router,
    jobs.router,
    companies.router,
    scrapers.router,
    llm.router,
    applications.router,
    skills.router,
    profile.router,
    app_settings.router,
    danger_zone.router,
    tasks.router,
    health.router,
    plugins.router,
    templates.router,
]

__all__ = [
    "applications",
    "app_settings",
    "companies",
    "danger_zone",
    "health",
    "jobs",
    "llm",
    "overview",
    "plugins",
    "profile",
    "scrapers",
    "skills",
    "tasks",
    "templates",
    "router_registry",
]

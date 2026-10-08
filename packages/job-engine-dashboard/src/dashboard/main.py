"""
Job Engine Dashboard — FastAPI + Vue 3 SPA.

Serves JSON REST API endpoints consumed by the Vue 3 frontend.
Built SPA assets are served from dist/ via StaticFiles + catch-all route.

Run with:
    make dashboard
    # or
    uvicorn dashboard.main:app --reload --port 8000

Or directly:
    python -m dashboard.main
"""

import logging
import os
import sys
from collections.abc import Generator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

# Load .env before anything else — common.py also loads it, but this ensures
# it runs before any route module import that might need env vars.
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from job_engine import __version__ as _app_version
from job_engine.database import get_sync_engine as get_engine
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Project root & sys.path
# ---------------------------------------------------------------------------

_root = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(_root / "config" / ".env")

if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging (respects LOG_LEVEL env var, defaults to INFO)
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting Job Engine Dashboard")
    """Startup: create DB tables if missing, initialize scraper manager and task manager.
    Shutdown: kill active scrapers and tasks.
    """
    from job_engine.database import init_db_sync
    from job_engine.scraper_runner import get_scraper_manager
    from job_engine.task_manager import get_task_manager

    init_db_sync()
    manager = get_scraper_manager()
    # Ensure the unified TaskManager is ready before any route requests arrive
    get_task_manager()
    # Discover + enable plugins from data/plugins.yml before any route requests
    # A broken plugin config fails startup loudly rather than silently disabling plugins.
    from job_engine.plugin_loader import get_plugin_loader

    plugin_count = get_plugin_loader().init_plugins()
    logger.info("Plugins initialized (%d enabled)", plugin_count)
    logger.info("TaskManager initialized ready for background tasks")
    yield
    await manager.shutdown()


app = FastAPI(
    title="Job Engine Dashboard",
    description="Track scraped jobs, match scores, and applications",
    version=_app_version,
    lifespan=lifespan,
)

# Scraper registry/catalog failures raise instead of returning empty fallbacks;
# surface them as explicit HTTP errors with the real cause in the detail.
from fastapi.responses import JSONResponse as _JSONResponse  # noqa: E402
from job_engine.scraper_config import ScraperCatalogError, ScraperRegistryError  # noqa: E402


@app.exception_handler(ScraperRegistryError)
async def _scraper_registry_error_handler(request, exc: ScraperRegistryError):
    return _JSONResponse(status_code=503, content={"detail": f"Scraper registry error: {exc}"})


@app.exception_handler(ScraperCatalogError)
async def _scraper_catalog_error_handler(request, exc: ScraperCatalogError):
    return _JSONResponse(status_code=502, content={"detail": f"Scraper catalog error: {exc}"})


# Mount static files
_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Mount Vue SPA build output (production) — assets are at /assets/...
_vue_dist = Path(__file__).resolve().parent.parent.parent / "dist"
if _vue_dist.exists() and _vue_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_vue_dist / "assets")), name="vue_assets")

# ---------------------------------------------------------------------------
# Register route modules
# ---------------------------------------------------------------------------


from dashboard.routes import router_registry  # noqa: E402

for router in router_registry:
    app.include_router(router)

# ---------------------------------------------------------------------------
# Common FastAPI dependencies
# ---------------------------------------------------------------------------


def get_db() -> Generator[Session, None, None]:
    """Yields a synchronous SQLAlchemy session. Use with FastAPI Depends()."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Vue SPA catch-all — serve index.html for frontend routes
# (API and static routes take precedence via earlier registration)
# ---------------------------------------------------------------------------


@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def vue_spa(full_path: str):
    """Serve the Vue SPA index.html for any frontend route not matched above."""
    # Only handle SPA routes — API and static routes are matched first
    _vue_index = Path(__file__).resolve().parent.parent.parent / "dist" / "index.html"
    if _vue_index.exists():
        return HTMLResponse(content=_vue_index.read_text(encoding="utf-8"))
    # Fallback: return a minimal page so the app isn't completely broken
    return HTMLResponse(
        content="""<!DOCTYPE html><html><body>
        <p>Vue SPA not built yet. Run:
        <code>cd packages/job-engine-dashboard &amp;&amp; npm run build</code></p>
        </body></html>"""
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    """Run the dashboard server."""
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("RELOAD", "1") != "0"
    print(f"Job Engine Dashboard: http://localhost:{port}")
    if reload:
        uvicorn.run("dashboard.main:app", host="0.0.0.0", port=port, reload=True)
    else:
        uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()

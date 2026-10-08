"""Plugin management API routes.

Exposes the plugin registry (see ``job_engine.plugin`` and
``job_engine.plugin_loader``) over HTTP for the dashboard:
- ``GET /api/plugins`` — list installed plugins with enable state
- ``POST /api/plugins/{name}/enable`` / ``.../disable`` — toggle enable state
- ``POST /api/plugins/discover`` — force re-discovery of plugin modules

Plugin *code* (custom analyzers, output formatters, integrations) drops into
``data/plugins/*.py``; this API manages which are active. Individual hooks
fire automatically in the core pipeline (analysis + application lifecycle).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from job_engine.plugin_loader import get_plugin_loader

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/plugins")
async def api_list_plugins():
    """List installed plugins and their enabled state."""
    plugins = get_plugin_loader().list_plugins()
    return JSONResponse(plugins)


@router.post("/api/plugins/{name}/enable")
async def api_enable_plugin(name: str):
    """Enable a plugin by name."""
    loader = get_plugin_loader()
    present = loader.set_enabled(name, True)
    if not present:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{name}' is not installed or could not be loaded",
        )
    return JSONResponse({"status": "ok", "name": name, "enabled": True})


@router.post("/api/plugins/{name}/disable")
async def api_disable_plugin(name: str):
    """Disable a plugin by name."""
    loader = get_plugin_loader()
    present = loader.set_enabled(name, False)
    if not present and name not in loader.list_plugins():
        # Name may be unknown entirely — still allow disabling (idempotent guard)
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return JSONResponse({"status": "ok", "name": name, "enabled": False})


@router.post("/api/plugins/discover")
async def api_discover_plugins():
    """Re-scan data/plugins for modules and reconcile enable state."""
    count = get_plugin_loader().init_plugins()
    return JSONResponse({"status": "ok", "enabled_count": count})

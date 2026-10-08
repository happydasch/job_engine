"""
Scraper catalog Configuration — read/write scraper catalog definitions.

Reads data/scraper_catalogs.yaml and provides a clean API for managing
catalog definitions (npm registries, local paths, git repos) that serve
as sources for installing scraper packages.

Usage:
    catalogs = load_catalogs()
    default = get_default_catalog()
    add_catalog({"id": "my-reg", "type": "npm", "scope": "@my-org"})
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from job_engine.config import config

logger = logging.getLogger(__name__)

# Shared round-trip YAML loader — preserves comments and key order on write.
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


# ── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class CatalogDef:
    """Definition of a scraper catalog (source of scraper packages)."""

    id: str
    name: str
    type: str  # "npm" | "local" | "git"
    enabled: bool = True

    # npm type fields
    scope: str = ""
    registry: str = "https://registry.npmjs.org"

    # local type fields
    path: str = ""

    # git type fields
    url: str = ""
    ref: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CatalogDef":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", d.get("id", "")),
            type=d.get("type", "npm"),
            enabled=d.get("enabled", True),
            scope=d.get("scope", ""),
            registry=d.get("registry", "https://registry.npmjs.org"),
            path=d.get("path", ""),
            url=d.get("url", ""),
            ref=d.get("ref", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
        }
        if self.type == "npm":
            base["scope"] = self.scope
            base["registry"] = self.registry
        elif self.type == "local":
            base["path"] = self.path
        elif self.type == "git":
            base["url"] = self.url
            base["ref"] = self.ref
        return base


# ── Path ─────────────────────────────────────────────────────────────────────

_CATALOGS_PATH: Path | None = None


def _get_catalogs_path() -> Path:
    global _CATALOGS_PATH
    if _CATALOGS_PATH is None:
        _CATALOGS_PATH = config.project_root / "data" / "scraper_catalogs.yaml"
    return _CATALOGS_PATH


# ── Load / Save ─────────────────────────────────────────────────────────────


def load_catalogs() -> list[CatalogDef]:
    """Load all catalog definitions from scraper_catalogs.yaml.

    Auto-seeds the bundled local catalog when no config file exists yet,
    so a fresh checkout immediately shows available scrapers in the Catalog tab.
    """
    path = _get_catalogs_path()
    try:
        if not path.exists():
            # Fall back to template in config/ if no data/ copy exists yet
            template = config.project_root / "config" / "scraper_catalogs.yaml"
            if template.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(template.read_bytes())
            else:
                # Auto-seed the bundled local catalog so the Catalog tab is
                # immediately usable on a fresh checkout.
                logger.info("No scraper catalogs found — auto-seeding bundled catalog")
                bundled = CatalogDef(
                    id="bundled",
                    name="Bundled job-engine-scrapers",
                    type="local",
                    enabled=True,
                    path="packages/job-engine-scrapers/scrapers",
                )
                save_catalogs([bundled])
                return [bundled]
        with open(path) as f:
            parsed = _yaml.load(f)
        if not parsed or not isinstance(parsed, dict):
            return []
        raw_catalogs = parsed.get("catalogs", [])
        if not isinstance(raw_catalogs, list):
            return []
        return [CatalogDef.from_dict(s) for s in raw_catalogs if isinstance(s, dict)]
    except Exception as exc:
        logger.warning("Failed to load catalog config: %s", exc)
        raise


def save_catalogs(catalogs: list[CatalogDef]) -> bool:
    """Save catalogs definitions to scraper_catalogs.yaml.

    Returns True on success.
    """
    path = _get_catalogs_path()
    try:
        doc = {"catalogs": [s.to_dict() for s in catalogs]}
        with open(path, "w") as f:
            _yaml.dump(doc, f)
        return True
    except Exception as exc:
        logger.warning("Failed to save catalog config: %s", exc)
        raise


# ── Lookup ───────────────────────────────────────────────────────────────────


def get_catalog(catalog_id: str) -> CatalogDef | None:
    """Get a catalog by ID."""
    for c in load_catalogs():
        if c.id == catalog_id:
            return c
    return None


def get_default_catalog() -> CatalogDef | None:
    """Get the first enabled catalog (the default).

    Falls back to the first catalog overall if none are enabled.
    """
    catalogs = load_catalogs()
    for s in catalogs:
        if s.enabled:
            return s
    return catalogs[0] if catalogs else None


def list_catalogs(enabled_only: bool = False) -> list[CatalogDef]:
    """Get all catalogs, or only enabled ones."""
    catalogs = load_catalogs()
    if enabled_only:
        return [c for c in catalogs if c.enabled]
    return catalogs


# ── CRUD ─────────────────────────────────────────────────────────────────────


_VALID_TYPES = {"npm", "local", "git"}


def add_catalog(defn: CatalogDef | dict[str, Any]) -> dict[str, Any]:
    """Add a catalog definition.

    Accepts a CatalogDef object or a dict.

    Returns {"success": True} on success, or {"success": False, "error": ...}.
    """
    if isinstance(defn, dict):
        defn = CatalogDef.from_dict(defn)

    if not defn.id or not defn.type:
        return {"success": False, "error": "Catalog must have 'id' and 'type' fields"}

    if defn.type not in _VALID_TYPES:
        return {
            "success": False,
            "error": f"Invalid catalog type '{defn.type}'. "
            f"Must be one of: {', '.join(sorted(_VALID_TYPES))}",
        }

    catalogs = load_catalogs()
    if any(c.id == defn.id for c in catalogs):
        return {"success": False, "error": f"Catalog '{defn.id}' already exists"}

    catalogs.append(defn)
    if save_catalogs(catalogs):
        return {"success": True}
    return {"success": False, "error": "Failed to write catalog config"}


def remove_catalog(catalog_id: str) -> dict[str, Any]:
    """Remove a catalog by ID.

    Returns {"success": True} on success, or {"success": False, "error": ...}.
    """
    catalogs = load_catalogs()
    before = len(catalogs)
    catalogs = [c for c in catalogs if c.id != catalog_id]
    if len(catalogs) == before:
        return {"success": False, "error": f"Catalog '{catalog_id}' not found"}
    if save_catalogs(catalogs):
        return {"success": True}
    return {"success": False, "error": "Failed to write catalog config"}


def update_catalog(catalog_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update a catalog's configuration.

    Only the fields present in ``updates`` are changed.
    Returns {"success": True} on success, or {"success": False, "error": ...}.
    """
    catalogs = load_catalogs()
    idx = next((i for i, c in enumerate(catalogs) if c.id == catalog_id), -1)
    if idx == -1:
        return {"success": False, "error": f"Catalog '{catalog_id}' not found"}

    catalog = catalogs[idx]
    allowed = {"name", "type", "scope", "registry", "path", "url", "ref", "enabled"}

    for key, value in updates.items():
        if key in allowed:
            setattr(catalog, key, value)

    catalogs[idx] = catalog
    if save_catalogs(catalogs):
        return {"success": True}
    return {"success": False, "error": "Failed to write catalog config"}

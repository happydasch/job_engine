"""
Scraper configuration management for dashboard-controlled scrapers.

Reads and writes the scraper_config.yaml file to enable/disable individual
scrapers from the dashboard UI. The Node.js config.js already
reads the `enabled` flag from this file, so toggling here takes effect
on the next scraper run.

Scraper metadata (IDs, labels) is sourced from the Node.js ScraperRegistry
via `node scrapers/dump-metadata.js`. There is no fallback: a registry
query failure raises ScraperRegistryError.

Usage:
    cfg = get_scraper_config()
    scrapers = cfg.list_scrapers()       # [{"id": ..., "enabled": ...}, ...]
    cfg.toggle_scraper("upwork")          # flips enabled
    cfg.set_scraper("upwork", True)       # sets to True
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_engine.config import config
from job_engine.database import get_sync_engine
from job_engine.models import Job, ScraperLog

logger = logging.getLogger(__name__)

# Shared round-trip YAML loader — preserves comments and key order on write.
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)

# No fallback scrapers — if no scrapers are registered, the list is empty.
# A broken environment (Node.js missing, dump-metadata.js failing, invalid
# output) raises ScraperRegistryError instead of masquerading as "no scrapers".


class ScraperRegistryError(RuntimeError):
    """The Node.js scraper registry could not be queried."""


class ScraperCatalogError(RuntimeError):
    """A scraper catalog could not be queried."""


# ── Registry metadata loader ────────────────────────────────────────────────

_CACHED_METADATA: list[dict[str, Any]] | None = None
_CACHED_METADATA_TIMESTAMP: float = 0
_METADATA_CACHE_TTL: float = 300.0  # seconds — 5 minutes


def _load_registry_metadata(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Run dump-metadata.js and return the parsed JSON array.

    An empty list means the registry genuinely has zero scrapers. Any failure
    to query it (Node.js missing, script error, timeout, unparseable output)
    raises ScraperRegistryError — no silent empty-list fallback.
    Result is cached with a TTL of 5 minutes; pass force_refresh=True
    to bypass the cache.
    """
    global _CACHED_METADATA, _CACHED_METADATA_TIMESTAMP

    if not force_refresh and _CACHED_METADATA is not None:
        age = time.time() - _CACHED_METADATA_TIMESTAMP
        if age < _METADATA_CACHE_TTL:
            return _CACHED_METADATA

    dump_script = config.project_root / "packages" / "job-engine-scrapers" / "dump-metadata.js"
    try:
        result = subprocess.run(
            ["node", str(dump_script)],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise ScraperRegistryError("Node.js not found — cannot query scraper registry") from exc
    except subprocess.CalledProcessError as exc:
        raise ScraperRegistryError(
            f"dump-metadata.js failed (exit {exc.returncode}): {exc.stderr or exc.stdout}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ScraperRegistryError("dump-metadata.js timed out after 30s") from exc

    raw = result.stdout.strip()
    # Use JSONDecoder.raw_decode to parse exactly one JSON value and
    # ignore any trailing output (e.g. from proxy.js async logging).
    try:
        data, _end_pos = json.JSONDecoder().raw_decode(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ScraperRegistryError(
            f"dump-metadata.js produced unparseable output: {raw[:300]}"
        ) from exc

    if not isinstance(data, list):
        raise ScraperRegistryError(
            f"dump-metadata.js returned {type(data).__name__}, expected a JSON array"
        )

    if len(data) == 0:
        logger.info("dump-metadata.js returned no registered scrapers (none installed yet)")

    _CACHED_METADATA = data
    _CACHED_METADATA_TIMESTAMP = time.time()
    return _CACHED_METADATA


# ── Scraper catalog (from catalog sources) ──────────────────────────────

_CACHED_CATALOG: list[dict[str, Any]] | None = None


def _load_catalog_data(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Query all enabled catalog sources for available scraper packages.

    An empty list means no catalogs are configured (or they contain nothing).
    A catalog that cannot be queried raises ScraperCatalogError — a broken catalog
    is an error to surface, not an empty catalog.

    Cached with a TTL of 5 minutes; pass force_refresh=True to bypass.
    """
    global _CACHED_CATALOG
    if not force_refresh and _CACHED_CATALOG is not None:
        return _CACHED_CATALOG

    from job_engine.scraper_catalog_config import list_catalogs

    catalogs = list_catalogs(enabled_only=True)
    if not catalogs:
        _CACHED_CATALOG = []
        return _CACHED_CATALOG

    all_scrapers: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for catalog in catalogs:
        if catalog.type == "npm":
            import httpx

            scope = catalog.scope or "@job-engine-scrapers"
            scope_name = scope.lstrip("@")
            search_url = f"{catalog.registry}/-/v1/search?text=scope:{scope_name}&size=250"
            try:
                resp = httpx.get(search_url, timeout=15.0)
            except httpx.HTTPError as exc:
                raise ScraperCatalogError(
                    f"npm catalog '{catalog.id}' unreachable ({search_url}): {exc}"
                ) from exc
            if resp.status_code != 200:
                raise ScraperCatalogError(
                    f"npm catalog '{catalog.id}' search failed with HTTP {resp.status_code}"
                )
            data = resp.json()
            for obj in data.get("objects", []):
                pkg = obj.get("package", {})
                pkg_name = pkg.get("name", "")
                if not pkg_name.startswith(f"{scope}/scraper-"):
                    continue
                pkg_id = pkg_name.replace(f"{scope}/scraper-", "")
                if pkg_id in seen_ids:
                    continue
                seen_ids.add(pkg_id)
                keywords = pkg.get("keywords", [])
                desc = pkg.get("description", f"Scraper {pkg_id}")
                links = pkg.get("links", {})
                version = pkg.get("version", "1.0.0")
                entry: dict[str, Any] = {
                    "id": pkg_id,
                    "name": pkg_name,
                    "description": desc,
                    "version": version,
                    "npmPackage": pkg_name,
                    "source": "npm",
                    "catalogId": catalog.id,
                    "catalogName": catalog.name,
                    "capabilities": [k for k in keywords if k in ("api", "browser", "fetch")],
                    "needsBrowser": "browser" in keywords,
                    "dataRichness": "high"
                    if "high" in keywords
                    else "medium"
                    if "medium" in keywords
                    else "low"
                    if "low" in keywords
                    else "unknown",
                    "category": next(
                        (k for k in ("polish", "crypto", "freelance", "remote") if k in keywords),
                        "other",
                    ),
                    "homepage": links.get("homepage", links.get("npm", "")),
                }
                all_scrapers.append(entry)
        elif catalog.type == "local":
            local_path = Path(catalog.path) if catalog.path else None
            if local_path and not local_path.is_absolute():
                # Relative paths resolve against the project root so the
                # default catalog config works regardless of cwd.
                local_path = config.project_root / local_path
            if not local_path or not local_path.exists():
                raise ScraperCatalogError(
                    f"local catalog '{catalog.id}' path does not exist: {local_path}"
                )
            try:
                entry_dirs = sorted(d for d in local_path.iterdir() if d.is_dir())
            except OSError as exc:
                raise ScraperCatalogError(
                    f"failed to scan local catalog '{catalog.id}' at {local_path}: {exc}"
                ) from exc
            for entry_dir in entry_dirs:
                pkg_json_path = entry_dir / "package.json"
                if not pkg_json_path.exists():
                    continue
                try:
                    pkg_data = json.loads(pkg_json_path.read_text())
                except (json.JSONDecodeError, OSError) as exc:
                    # A broken package in the catalog is an error to fix,
                    # not an entry to silently hide.
                    raise ScraperCatalogError(
                        f"unreadable package.json in catalog '{catalog.id}': {pkg_json_path}: {exc}"
                    ) from exc
                pkg_id = entry_dir.name.removeprefix("scraper-")
                if pkg_id in seen_ids:
                    continue
                seen_ids.add(pkg_id)
                keywords = pkg_data.get("keywords", [])
                # Rich catalog metadata lives in the package.json
                # "jobEngine" block; keywords are the fallback.
                je = pkg_data.get("jobEngine") or {}
                entry = {
                    "id": pkg_id,
                    "name": je.get("displayName") or pkg_data.get("name", pkg_id),
                    "description": pkg_data.get("description", f"Local scraper {pkg_id}"),
                    "version": pkg_data.get("version", "1.0.0"),
                    "npmPackage": pkg_data.get("name", f"@job-engine-scrapers/scraper-{pkg_id}"),
                    "source": "local",
                    "catalogId": catalog.id,
                    "catalogName": catalog.name,
                    "capabilities": je.get("capabilities")
                    or [k for k in keywords if k in ("api", "browser", "fetch")],
                    "needsBrowser": je.get("needsBrowser", "browser" in keywords),
                    "dataRichness": je.get("dataRichness")
                    or (
                        "high"
                        if "high" in keywords
                        else "medium"
                        if "medium" in keywords
                        else "low"
                        if "low" in keywords
                        else "unknown"
                    ),
                    "category": je.get("category")
                    or next(
                        (k for k in ("polish", "crypto", "freelance", "remote") if k in keywords),
                        "other",
                    ),
                    "homepage": je.get("homepage") or pkg_data.get("homepage", ""),
                }
                all_scrapers.append(entry)
        # git catalogs: cannot list without cloning, skip

    _CACHED_CATALOG = all_scrapers
    return _CACHED_CATALOG


def _load_catalog(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Load the scraper catalog from catalog sources.

    Queries all enabled catalog sources for available scraper packages.
    There is NO fallback catalog — if no catalogs are configured (or all
    catalogs return nothing), the catalog is empty. The default catalog
    config (config/scraper_catalogs.yaml) ships with a local catalog
    pointing at the bundled scrapers directory.
    """
    return _load_catalog_data(force_refresh=force_refresh)


def get_catalog_scrapers() -> list[dict[str, Any]]:
    """Return all scrapers from the scraper catalog with installed status.

    Each entry includes catalog fields plus 'installed' boolean determined
    by checking whether the scraper is registered in the Node.js registry.
    Also includes 'version' from the catalog and 'installed_version' read
    from the active scraper's package.json.
    """
    catalog = _load_catalog(force_refresh=False)
    if not catalog:
        return []

    # Get installed IDs from registry metadata
    registry_ids = set(get_scraper_ids())

    result = []
    for entry in catalog:
        entry_id = entry["id"]
        # Read installed version from active-scrapers/<id>/package.json.
        # A corrupt package.json for an installed scraper is a broken
        # install — raise rather than displaying it as "unknown version".
        installed_version = None
        if entry_id in registry_ids:
            active_pkg = (
                config.project_root / "data" / "active-scrapers" / entry_id / "package.json"
            )
            if active_pkg.exists():
                try:
                    installed_version = json.loads(active_pkg.read_text()).get("version")
                except (json.JSONDecodeError, OSError) as exc:
                    raise ScraperCatalogError(
                        f"unreadable package.json for installed scraper "
                        f"'{entry_id}': {active_pkg}: {exc}"
                    ) from exc

        result.append(
            {
                "id": entry_id,
                "name": entry["name"],
                "description": entry.get("description", ""),
                "version": entry.get("version", "1.0.0"),
                "installed_version": installed_version,
                "npmPackage": entry.get("npmPackage", ""),
                "source": entry.get("source", "local"),
                "catalog_id": entry.get("catalogId", ""),
                "catalog_name": entry.get("catalogName", ""),
                "capabilities": entry.get("capabilities", []),
                "needsBrowser": entry.get("needsBrowser", False),
                "dataRichness": entry.get("dataRichness", "unknown"),
                "category": entry.get("category", "other"),
                "homepage": entry.get("homepage", ""),
                "installed": entry_id in registry_ids,
            }
        )
    return result


def refresh_catalog_cache() -> None:
    """Force a refresh of the cached catalog data."""
    _load_catalog(force_refresh=True)


# ── Install/Uninstall Scraper ───────────────────────────────────────────────


def install_scraper(scraper_id: str) -> dict[str, Any]:
    """Install a scraper by calling the Node.js install-scraper CLI.

    Returns {"success": True, "version": "..."} on success, or {"success": False, "error": ...}
    on failure.
    """
    install_script = config.project_root / "packages" / "job-engine-scrapers" / "install-scraper.js"
    cfg = ScraperConfig()
    enabled_map = cfg._load_enabled()
    was_known = scraper_id in enabled_map
    previous_enabled = enabled_map.get(scraper_id, False)
    try:
        result = subprocess.run(
            ["node", str(install_script), scraper_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            refresh_scraper_metadata()
            if was_known:
                # Reinstall: preserve whatever enabled state it already had —
                # a routine reinstall/update must not silently disable a
                # scraper the user was relying on.
                cfg.set_scraper(scraper_id, previous_enabled)
            else:
                # A brand-new scraper the user just explicitly chose to
                # install — enable it immediately so it's ready to run
                # without a second manual step.
                cfg.set_scraper(scraper_id, True)
            # Read the installed version from the active scraper's package.json.
            # An install that leaves no readable package.json behind is broken.
            active_pkg = (
                config.project_root / "data" / "active-scrapers" / scraper_id / "package.json"
            )
            try:
                version = json.loads(active_pkg.read_text()).get("version", "1.0.0")
            except (json.JSONDecodeError, OSError) as exc:
                return {
                    "success": False,
                    "error": f"Install left no readable package.json at {active_pkg}: {exc}",
                }
            return {"success": True, "version": version, "output": result.stdout}
        else:
            return {"success": False, "error": result.stderr or result.stdout}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Installation timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "Node.js not found"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def uninstall_scraper(scraper_id: str) -> dict[str, Any]:
    """Uninstall a scraper by calling the Node.js install-scraper CLI.

    Returns {"success": True} on success, or {"success": False, "error": ...}
    on failure.
    """
    install_script = config.project_root / "packages" / "job-engine-scrapers" / "install-scraper.js"
    try:
        result = subprocess.run(
            ["node", str(install_script), "--uninstall", scraper_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            refresh_scraper_metadata()
            return {"success": True, "output": result.stdout}
        else:
            return {"success": False, "error": result.stderr or result.stdout}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Uninstall timed out"}
    except FileNotFoundError:
        return {"success": False, "error": "Node.js not found"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def reinstall_scraper(scraper_id: str) -> dict[str, Any]:
    """Reinstall a single scraper by uninstalling then installing it.

    Returns ``{"success": True, "version": "..."}`` on success, or
    ``{"success": False, "error": ...}`` on failure.
    """
    # Uninstall
    uninstall_result = uninstall_scraper(scraper_id)
    if not uninstall_result["success"]:
        return {
            "success": False,
            "error": uninstall_result.get("error", "Uninstall failed"),
        }

    # Reinstall
    install_result = install_scraper(scraper_id)
    if install_result["success"]:
        return {
            "success": True,
            "version": install_result.get("version", ""),
            "output": install_result.get("output", ""),
        }
    else:
        return {
            "success": False,
            "error": install_result.get("error", "Reinstall failed"),
        }


def reinstall_all_scrapers() -> dict[str, Any]:
    """Reinstall every currently installed scraper.

    Uninstalls then reinstalls each scraper sequentially and returns a
    summary with per-scraper results and overall success/failure counts.
    """
    installed_ids = get_scraper_ids()
    if not installed_ids:
        return {
            "success": True,
            "message": "No scrapers installed",
            "results": [],
            "total": 0,
            "succeeded": 0,
            "failed": 0,
        }

    results: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0

    for scraper_id in installed_ids:
        # Uninstall
        uninstall_result = uninstall_scraper(scraper_id)
        if not uninstall_result["success"]:
            results.append(
                {
                    "id": scraper_id,
                    "success": False,
                    "step": "uninstall",
                    "error": uninstall_result.get("error", "Uninstall failed"),
                }
            )
            failed += 1
            continue

        # Reinstall
        install_result = install_scraper(scraper_id)
        if install_result["success"]:
            results.append(
                {
                    "id": scraper_id,
                    "success": True,
                    "step": "install",
                    "version": install_result.get("version", ""),
                }
            )
            succeeded += 1
        else:
            results.append(
                {
                    "id": scraper_id,
                    "success": False,
                    "step": "install",
                    "error": install_result.get("error", "Reinstall failed"),
                }
            )
            failed += 1

    return {
        "success": failed == 0,
        "message": f"Reinstalled {succeeded}/{len(installed_ids)} scrapers",
        "results": results,
        "total": len(installed_ids),
        "succeeded": succeeded,
        "failed": failed,
    }


# ── Derived lazy getters (replace module-level constants) ───────────────────


def get_scraper_ids() -> list[str]:
    """Return all known scraper IDs from the scraper registry."""
    return [p["id"] for p in _load_registry_metadata()]


def get_scraper_labels() -> dict[str, str]:
    """Return {id: name} mapping from the scraper registry."""
    return {p["id"]: p.get("name", p["id"]) for p in _load_registry_metadata()}


def refresh_scraper_metadata() -> None:
    """Force a refresh of the cached registry metadata.

    Call this when the scraper registry may have changed (e.g. after adding
    a new scraper).
    """
    _load_registry_metadata(force_refresh=True)


def _scrapers_block(data: dict[str, Any]) -> Any:
    """Return the scrapers mapping from a parsed YAML doc.

    Migrates the legacy 'platforms' key (old name for scrapers) in place so
    the next write persists the new key.
    """
    if "scrapers" not in data and "platforms" in data:
        data["scrapers"] = data.pop("platforms")
    return data.get("scrapers")


# ── ScraperConfig ────────────────────────────────────────────────────────


class ScraperConfig:
    """Read/write scraper enabled states in scraper_config.yaml."""

    def __init__(self, yaml_path: Path | None = None) -> None:
        self._yaml_path = yaml_path or (config.project_root / "data" / "scraper_config.yaml")
        self._cache: dict[str, bool] | None = None

    # ── Public API ────────────────────────────────────────────────────────

    def list_scrapers(self) -> list[dict[str, Any]]:
        """Return all known scrapers with their enabled state and last run info."""
        enabled_map = self._load_enabled()
        scraper_ids = get_scraper_ids()
        scraper_labels = get_scraper_labels()
        registry_meta = _load_registry_metadata()
        config_map = {p.get("id"): bool(p.get("configFields")) for p in registry_meta}

        # Build platform -> scraper_id mapping from registry metadata
        platform_to_scraper: dict[str, str] = {}
        for p in registry_meta:
            plat = p.get("platform")
            if plat:
                platform_to_scraper[plat] = p["id"]

        # Fetch the latest ScraperLog row per scraper. DB errors propagate —
        # a scraper list silently missing its run data hides real problems.
        last_run_map: dict[str, dict[str, Any]] = {}
        engine = get_sync_engine()
        with Session(engine) as session:
            # Subquery: max run_at per scraper
            subq = (
                select(ScraperLog.scraper, func.max(ScraperLog.run_at).label("max_run_at"))
                .where(~ScraperLog.scraper.like("dashboard_run_%"))
                .group_by(ScraperLog.scraper)
            ).subquery()
            # Join to get full latest row per scraper
            latest_rows = (
                session.execute(
                    select(ScraperLog).join(
                        subq,
                        (ScraperLog.scraper == subq.c.scraper)
                        & (ScraperLog.run_at == subq.c.max_run_at),
                    )
                )
                .scalars()
                .all()
            )
            for row in latest_rows:
                last_run_map[row.scraper] = {
                    "last_run_at": row.run_at.isoformat(),
                    "last_run_jobs_found": row.jobs_found,
                    "last_run_status": row.status,
                }

            # Count total jobs per platform
            platform_counts: dict[str, int] = {}
            for plat, pid in platform_to_scraper.items():
                cnt = session.execute(
                    select(func.count(Job.id)).where(Job.platform == plat)
                ).scalar()
                if cnt:
                    platform_counts[plat] = cnt

        result = []
        for pid in scraper_ids:
            entry = {
                "id": pid,
                "label": scraper_labels.get(pid, pid),
                "enabled": enabled_map.get(pid, True),
                "has_config": config_map.get(pid, False),
                "total_jobs": 0,
            }
            # Find matching platform for this scraper
            for plat, sid in platform_to_scraper.items():
                if sid == pid:
                    entry["total_jobs"] = platform_counts.get(plat, 0)
                    break
            if pid in last_run_map:
                entry.update(last_run_map[pid])
            result.append(entry)
        return result

    def get_active_ids(self) -> list[str]:
        """Return only scraper IDs that are enabled."""
        return [p["id"] for p in self.list_scrapers() if p["enabled"]]

    def toggle_scraper(self, scraper_id: str) -> bool | None:
        """Flip the enabled state for a scraper. Returns new state or None if not found."""
        scrapers = self.list_scrapers()
        match = next((p for p in scrapers if p["id"] == scraper_id), None)
        if match is None:
            return None
        new_state = not match["enabled"]
        self.set_scraper(scraper_id, new_state)
        return new_state

    def set_scraper(self, scraper_id: str, enabled: bool) -> bool:
        """Set a scraper's enabled state and persist to YAML. Returns the new state."""
        self._set_enabled_in_file(scraper_id, enabled)
        # Invalidate cache
        self._cache = None
        return enabled

    def ensure_config_file(self) -> None:
        """Create data/scraper_config.yaml if missing (all scrapers enabled)."""
        self._ensure_config_file()

    # ── Internal ──────────────────────────────────────────────────────────

    def _ensure_config_file(self) -> None:
        """Create data/scraper_config.yaml if it doesn't exist, with all
        known scrapers enabled by default.  No-op if the file already exists."""
        if self._yaml_path.exists():
            return

        scraper_ids = get_scraper_ids()
        if not scraper_ids:
            # No scrapers installed yet — create a minimal config so
            # subsequent operations (e.g. toggle) don't fail.
            self._yaml_path.parent.mkdir(parents=True, exist_ok=True)
            doc: dict[str, Any] = {"scrapers": {}}
            with self._yaml_path.open("w", encoding="utf-8") as fh:
                _yaml.dump(doc, fh)
            logger.info("Created empty %s", self._yaml_path)
            return

        self._yaml_path.parent.mkdir(parents=True, exist_ok=True)
        scrapers: dict[str, dict[str, bool]] = {}
        for pid in scraper_ids:
            scrapers[pid] = {"enabled": True}

        doc = {"scrapers": scrapers}
        with self._yaml_path.open("w", encoding="utf-8") as fh:
            _yaml.dump(doc, fh)
        logger.info("Created %s with %d scrapers enabled", self._yaml_path, len(scraper_ids))

    def _load_enabled(self) -> dict[str, bool]:
        """Parse scraper_config.yaml and return {scraper_id: enabled}."""
        if self._cache is not None:
            return self._cache

        # Ensure the config file exists before reading it; auto-creates
        # with all known scrapers enabled by default.
        self._ensure_config_file()

        scraper_ids = get_scraper_ids()
        registry = _load_registry_metadata()
        # Default: only scrapers explicitly in scraper_config.yaml are enabled.
        # Scrapers NOT in the YAML file default to False (disabled).
        default_map: dict[str, bool] = {}
        for p in registry:
            default_map[p["id"]] = p.get("configured", False)
        enabled_map: dict[str, bool] = {pid: default_map.get(pid, False) for pid in scraper_ids}

        if self._yaml_path.exists():
            with self._yaml_path.open("r", encoding="utf-8") as fh:
                data = _yaml.load(fh) or {}
            scrapers = _scrapers_block(data) or {}
            if isinstance(scrapers, dict):
                for pid, cfg in scrapers.items():
                    if pid not in get_scraper_ids():
                        continue
                    if isinstance(cfg, dict):
                        enabled_map[pid] = bool(cfg.get("enabled", True))
                    else:
                        # Bare "scraper_id:" with no body — treat as enabled.
                        enabled_map[pid] = True

        self._cache = enabled_map
        return enabled_map

    def _set_enabled_in_file(self, scraper_id: str, enabled: bool) -> None:
        """Set a scraper's enabled state in scraper_config.yaml.

        Uses ruamel round-trip load/dump, which preserves comments, ordering,
        and formatting.  If the scraper_id is not yet in the YAML file, a new
        entry is created so that toggling a scraper for the first time persists.
        """
        self._ensure_config_file()
        if not self._yaml_path.exists():
            raise FileNotFoundError(
                f"Cannot toggle scraper: {self._yaml_path} still missing after ensure"
            )

        with self._yaml_path.open("r", encoding="utf-8") as fh:
            data = _yaml.load(fh) or {}

        scrapers = _scrapers_block(data)
        if not isinstance(scrapers, dict):
            scrapers = {}
            data["scrapers"] = scrapers
        if scraper_id not in scrapers:
            scrapers[scraper_id] = {}

        block = scrapers[scraper_id]
        if isinstance(block, dict):
            block["enabled"] = enabled
        else:
            # Bare key with no mapping body — replace with a mapping.
            scrapers[scraper_id] = {"enabled": enabled}

        with self._yaml_path.open("w", encoding="utf-8") as fh:
            _yaml.dump(data, fh)

    # ── Per-scraper config field access ──────────────────────────────────────

    def get_scraper_config_fields(self, scraper_id: str) -> dict[str, Any] | None:
        """Return the configFields schema for a scraper from registry metadata."""
        registry = _load_registry_metadata()
        for p in registry:
            if p.get("id") == scraper_id:
                return p.get("configFields") or {}
        return None

    def get_scraper_full_config(self, scraper_id: str) -> dict[str, Any] | None:
        """Return the full YAML config block for a scraper (all fields, not just enabled)."""
        if not self._yaml_path.exists():
            return None
        with self._yaml_path.open("r", encoding="utf-8") as fh:
            data = _yaml.load(fh) or {}
        scrapers = _scrapers_block(data) or {}
        block = scrapers.get(scraper_id)
        if isinstance(block, dict):
            return block
        if block is None:
            return None
        # Bare key with no mapping body
        return {"enabled": True}

    def set_scraper_field(self, scraper_id: str, field: str, value: Any) -> bool:
        """Set an arbitrary field on a scraper's YAML block and persist.

        Uses ruamel round-trip load/dump, which preserves comments, ordering,
        and formatting.  If the scraper_id is not yet in the YAML file, a new
        entry is created. Returns True on success.
        """
        self._ensure_config_file()
        if not self._yaml_path.exists():
            raise FileNotFoundError(
                f"Cannot set field: {self._yaml_path} still missing after ensure"
            )

        with self._yaml_path.open("r", encoding="utf-8") as fh:
            data = _yaml.load(fh) or {}

        scrapers = _scrapers_block(data)
        if not isinstance(scrapers, dict):
            scrapers = {}
            data["scrapers"] = scrapers
        if scraper_id not in scrapers:
            scrapers[scraper_id] = {}

        block = scrapers[scraper_id]
        if isinstance(block, dict):
            block[field] = value
        else:
            # Bare key with no mapping body — replace with a mapping.
            scrapers[scraper_id] = {field: value}

        with self._yaml_path.open("w", encoding="utf-8") as fh:
            _yaml.dump(data, fh)

        # Invalidate cache
        self._cache = None
        return True


# ── Singleton ─────────────────────────────────────────────────────────────

_scraper_config: ScraperConfig | None = None


def get_scraper_config() -> ScraperConfig:
    """Lazy-init singleton."""
    global _scraper_config
    if _scraper_config is None:
        _scraper_config = ScraperConfig()
    return _scraper_config
